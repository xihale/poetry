import { fetchBytes, fetchJson } from '~/utils/bytes'
import { CORPUS_N, CORPUS_ORDER, CORPUS_PER_CHUNK } from '~/corpus-meta'
import { AXES } from '~/types/poem'
import type { Axis, Filter, Poem } from '~/types/poem'
import { axisOrder } from '~/composables/facets'

/**
 * The corpus is 125,314 poems and it is not one file. Four kinds of artifact
 * carry it, and a reader pays for the ones their reading actually asks for
 * (scripts/build-corpus.py is where they are written):
 *
 *   facets.json.gz      every axis's choices and how many poems each one holds,
 *                       counted at build time. Opening 分类 with nothing
 *                       filtered is one small request and no work at all —
 *                       a count over the whole corpus is a fact about the
 *                       corpus, not something to recompute per reader.
 *   col/<axis>.bin.gz   one axis's codes, one per poem: 125 KB for a byte-wide
 *                       axis, 250 KB for a two-byte one. A filter needs these,
 *                       and only for the axes it names.
 *   t/NNNNN.json.gz     twenty poems' title, verse and labels, together. This
 *                       is the only file a draw needs.
 *   search/*.bin.gz     the bigram index (useSearch.ts).
 *
 * Two consequences are worth stating plainly. A reader who draws one poem
 * without filtering, searching or opening 分类 fetches about 3 KB: the labels
 * ride in the chunk beside the verse, so there is no index to load first and
 * nothing to keep in memory between poems. And filtering is the one thing that
 * has to look at every poem, so `pool` and `facet` are only answerable after
 * `ready` has fetched the columns they will look at — a filter is a request,
 * not a computation over what already happens to be on hand.
 *
 * What the browser holds is therefore proportional to what has been asked for:
 * nothing at all for a reader who reads, and 1.6 MB of codes — 201 KB on the
 * wire — for one who filters by every axis at once. That is the trade this
 * format makes, and it is the right way round: every reader draws a poem, few
 * narrow the whole canon.
 */

/**
 * One poem as a chunk stores it. Short keys, because there are 125,314 of them.
 *
 * `l` is the labels, positional in CORPUS_ORDER: the build writes them in that
 * order and this file reads them by name through it, so the two can only
 * disagree if the generated file is stale — never because a position was
 * miscounted by hand.
 */
export interface PoemText {
  /** title */
  t: string
  /** the verse */
  x: string
  /** characters */
  c: number
  /** the poem in its own language, when the leaf prints a translation beside it */
  o?: string
  /** 解题 */
  n?: string
  /** the labels, positional in CORPUS_ORDER; a multi-valued axis is an array */
  l: (string | string[])[]
}

interface PackedAxis {
  dict: string[]
  w: 1 | 2
  multi: boolean
  /** how many poems carry each value, over the whole corpus */
  counts: number[]
}

interface Facets {
  v: string
  n: number
  order: string[]
  multi: string[]
  byAxis: Partial<Record<Axis, PackedAxis>>
}

/** The multi-valued axes, as a set: 情绪 and 视角 are bitfields, not indices. */
const MULTI = new Set<string>(['mood', 'view'])

/**
 * The arrays are written little-endian and a TypedArray reads the platform's
 * own order, so a big-endian host would read every code wrong. No browser ships
 * on one — but the format says little-endian, and a reader is entitled to the
 * bytes it was promised.
 */
const BIG_ENDIAN = new Uint8Array(new Uint16Array([1]).buffer)[0] === 0

/** Where each axis's label sits in a chunk's positional list. */
const POSITION = new Map<string, number>(CORPUS_ORDER.map((axis, at) => [axis, at]))

export interface FacetCount {
  values: string[]
  counts: Map<string, number>
  total: number
}

export interface Corpus {
  n: number
  /**
   * Whether one axis carries a value at all. A filter can name a value the
   * corpus does not have — an address outlives the corpus it was written
   * against — and this is what tells the two apart. Needs the dictionaries,
   * which `ready` loads.
   */
  has(axis: Axis, value: string): boolean
  /** the poems a filter leaves, as indices into the corpus */
  pool(filter: Filter): Uint32Array
  /** one axis's choices and how many poems each would leave */
  facet(filter: Filter, axis: Axis): FacetCount
  /** a whole poem, text and labels together */
  poem(i: number): Promise<Poem>
  /**
   * Load what a filter will be answered from: the axes it names, plus — when
   * `counting` is given — the columns the choices of those axes are counted
   * out of. See the note on the implementation for why an empty `counting` is
   * still a request.
   */
  ready(filter: Filter, counting?: Axis[]): Promise<void>
}

let pending: Promise<Corpus> | null = null

/**
 * The corpus, shared by everything that needs it. Client-only: the poem is
 * chosen per visit so there is nothing to render ahead of time, and no part of
 * the corpus belongs in the document.
 */
export function useCorpus(): Promise<Corpus> {
  pending ??= create()
  return pending
}

async function create(): Promise<Corpus> {
  /** The columns, once fetched. Each is kept for the life of the page. */
  const cols = new Map<string, Uint8Array | Uint16Array>()
  const colFlights = new Map<string, Promise<Uint8Array | Uint16Array>>()
  /** The choices of each axis, and where each value sits in its dictionary. */
  let facets: Facets | null = null
  let facetsFlight: Promise<Facets> | null = null
  const positions = new Map<string, Map<string, number>>()

  const chunks = new Map<number, Promise<PoemText[]>>()
  const loaded = new Map<number, Poem>()

  function loadFacets(): Promise<Facets> {
    facetsFlight ??= fetchJson<Facets>('/corpus/facets.json.gz').then((got) => {
      for (const [axis, packed] of Object.entries(got.byAxis)) {
        positions.set(axis, new Map(packed.dict.map((v, at) => [v, at])))
      }
      return (facets = got)
    })
    return facetsFlight
  }

  /**
   * A column's width is read from its own length rather than from facets.json,
   * so a column can be fetched without waiting for anything else — and a file
   * that is neither length is a build that half-happened, which is worth
   * failing loudly over rather than reading as if it were short.
   */
  function view(bytes: Uint8Array, axis: string): Uint8Array | Uint16Array {
    if (bytes.length === CORPUS_N) return bytes
    if (bytes.length !== CORPUS_N * 2) {
      throw new Error(
        `corpus/col/${axis}.bin.gz is ${bytes.length} bytes; ` +
        `${CORPUS_N} or ${CORPUS_N * 2} were expected`)
    }
    // a Uint16Array view has to start on an even byte, and one handed back by
    // the decompressor is not guaranteed to
    if (bytes.byteOffset % 2 === 0) return new Uint16Array(bytes.buffer, bytes.byteOffset, CORPUS_N)
    const even = new Uint8Array(bytes.length)
    even.set(bytes)
    return new Uint16Array(even.buffer)
  }

  function loadColumn(axis: string): Promise<Uint8Array | Uint16Array> {
    const hit = cols.get(axis)
    if (hit) return Promise.resolve(hit)
    let flight = colFlights.get(axis)
    if (!flight) {
      flight = fetchBytes(`/corpus/col/${axis}.bin.gz`).then((bytes) => {
        const codes = view(bytes, axis)
        if (BIG_ENDIAN) {
          for (let i = 0; i < codes.length; i++) codes[i] = (codes[i]! >> 8) | ((codes[i]! & 0xff) << 8)
        }
        cols.set(axis, codes)
        colFlights.delete(axis)
        return codes
      })
      colFlights.set(axis, flight)
    }
    return flight
  }

  /**
   * A column that the caller has already been promised is loaded. `ready` is
   * what makes this true, so reaching here without it is a programming error
   * and is worth the exception: the alternative is a silently wrong answer —
   * an unfiltered pool, a count of nothing — which the reader would see as a
   * collection that does not exist.
   */
  function column(axis: Axis): Uint8Array | Uint16Array {
    const hit = cols.get(axis)
    if (!hit) throw new Error(`corpus: ${axis} column not loaded — await ready() first`)
    return hit
  }

  function position(axis: Axis, value: string): number {
    const at = positions.get(axis)?.get(value)
    if (at === undefined) {
      throw new Error(`corpus: ${axis} has no value ${JSON.stringify(value)} — await ready() first`)
    }
    return at
  }

  /**
   * Whether the axis carries the value. `position` throws on a value that is
   * not there, which is right for a filter this app built and wrong for a
   * filter that arrived in someone's address — so the question is asked here,
   * before a filter naming a poet who is gone is ever used to read a column.
   */
  function has(axis: Axis, value: string): boolean {
    return positions.get(axis)?.has(value) ?? false
  }

  /** Whether one poem carries the filter's value on one axis. */
  function carries(i: number, axis: Axis, want: string): boolean {
    if (MULTI.has(axis)) return (column(axis)[i]! & (1 << position(axis, want))) !== 0
    return column(axis)[i] === position(axis, want)
  }

  /** The whole corpus as a pool, built once and never rebuilt. */
  let everything: Uint32Array | null = null

  /**
   * The pool a filter leaves, remembered.
   *
   * The panel asks for a count on every axis under one filter, and every one of
   * those counts starts from the same set of poems — so the scan happens once
   * and the ten counts walk the same list. Without this, each axis re-tested
   * all 125,314 poems against the filter. The pool is also what the stream
   * draws from, so applying a filter and recounting the panel share one scan.
   */
  let memoKey = ''
  let memoPool: Uint32Array | null = null

  function poolOf(filter: Filter): Uint32Array {
    const key = AXES.map((a) => (filter[a.key] ? `${a.key}=${filter[a.key]}` : '')).join('|')
    if (key === memoKey && memoPool) return memoPool
    const active = AXES.map((a) => a.key).filter((k) => filter[k])
    let out: Uint32Array
    if (!active.length) {
      if (!everything) {
        everything = new Uint32Array(CORPUS_N)
        for (let i = 0; i < CORPUS_N; i++) everything[i] = i
      }
      out = everything
    } else {
      // The scratch array is the size of the corpus because a filter can leave
      // most of it; trimming the tail is one copy of what is kept, where
      // growing a plain array a push at a time would be thousands of them.
      const kept = new Uint32Array(CORPUS_N)
      let at = 0
      for (let i = 0; i < CORPUS_N; i++) {
        let ok = true
        for (const axis of active) {
          if (!carries(i, axis, filter[axis]!)) { ok = false; break }
        }
        if (ok) kept[at++] = i
      }
      out = at === CORPUS_N ? kept : kept.slice(0, at)
    }
    memoKey = key
    memoPool = out
    return out
  }

  function pool(filter: Filter): Uint32Array {
    return poolOf(filter)
  }

  /**
   * One axis's choices and their counts, given the other axes.
   *
   * A poem counts toward an axis's value when it matches the filter on *every
   * other* axis — so a poem that fails one axis is still counted under that
   * axis's own value, which is exactly the question the panel is asking. Poems
   * failing two axes count nowhere.
   */
  function facet(filter: Filter, axis: Axis): FacetCount {
    const packed = facets?.byAxis[axis]
    if (!packed) throw new Error('corpus: facets not loaded — await ready() first')
    const dict = packed.dict
    const counts = new Map<string, number>()
    const others = AXES.map((a) => a.key).filter((key) => key !== axis && filter[key])

    if (!others.length) {
      // Nothing is narrowing this axis, so its counts do not depend on the
      // reader or on anything else they have chosen — they are the corpus's own
      // numbers, counted once at build time. This is the path 分类 takes when it
      // opens on a fresh page, and it is why the panel can open without
      // fetching a single column.
      dict.forEach((value, at) => {
        const n = packed.counts[at]!
        if (n) counts.set(value, n)
      })
      return { values: [...counts.keys()].sort(axisOrder(axis)), counts, total: CORPUS_N }
    }

    // the axis's own filter is not part of what it counts, so drop it
    const ids = filter[axis] ? poolOf({ ...filter, [axis]: null }) : poolOf(filter)
    // Counted in an array indexed by the value's code, not in a Map keyed by the
    // value: the tally is what runs millions of times, and building the Map once
    // from the finished tally is a few dozen map writes instead of hundreds of
    // thousands.
    const tally = new Int32Array(dict.length)
    for (const i of ids) {
      if (packed.multi) {
        const bits = column(axis)[i]!
        for (let at = 0; at < tally.length; at++) {
          if (bits & (1 << at)) tally[at] = (tally[at] ?? 0) + 1
        }
      } else {
        const at = column(axis)[i]!
        tally[at] = (tally[at] ?? 0) + 1
      }
    }
    tally.forEach((n, at) => {
      if (n) counts.set(dict[at]!, n)
    })

    return { values: [...counts.keys()].sort(axisOrder(axis)), counts, total: ids.length }
  }

  /**
   * Twenty poems to a file, numbered from zero. A drawn poem almost never shares
   * its file with the last one — the draw is random — so this is the file a page
   * turn pays for, and why it is twenty and not two hundred.
   */
  function chunkOf(i: number): Promise<PoemText[]> {
    const at = Math.floor(i / CORPUS_PER_CHUNK)
    let hit = chunks.get(at)
    if (!hit) {
      hit = fetchJson<PoemText[]>(`/corpus/t/${String(at).padStart(5, '0')}.json.gz`)
      chunks.set(at, hit)
    }
    return hit
  }

  /** One label of one poem, read out of the chunk that carries it. */
  function label(t: PoemText, axis: string): string {
    const value = t.l[POSITION.get(axis)!]
    return typeof value === 'string' ? value : ''
  }

  /**
   * The values of a multi-valued axis, in the order the build ranked them —
   * 愁 before 思, the way the lexicon was written — which is an order worth
   * keeping and not one to sort into an alphabet.
   */
  function words(t: PoemText, axis: string): string[] {
    const value = t.l[POSITION.get(axis)!]
    return Array.isArray(value) ? value : []
  }

  async function poem(i: number): Promise<Poem> {
    const hit = loaded.get(i)
    if (hit) return hit
    const t = await chunkOf(i).then((chunk) => chunk[i % CORPUS_PER_CHUNK]!)
    const lang = label(t, 'lang')
    const olang = label(t, 'olang')
    const out: Poem = {
      id: i,
      title: t.t,
      text: t.x,
      chars: t.c,
      note: t.n ?? '',
      author: label(t, 'author'),
      era: label(t, 'era'),
      coll: label(t, 'coll'),
      cat: label(t, 'cat'),
      juan: label(t, 'juan'),
      chapter: label(t, 'chapter'),
      form: label(t, 'form'),
      len: label(t, 'len'),
      mood: words(t, 'mood'),
      view: words(t, 'view'),
      lang: lang || '中文',
      ...(olang ? { olang } : {}),
      ...(t.o ? { orig: t.o } : {}),
    }
    loaded.set(i, out)
    return out
  }

  /**
   * Load what a filter will be answered from: the choices on every axis, the
   * columns of the axes the filter names, and — when `counting` is given — the
   * columns of the axes whose choices are about to be shown.
   *
   * `counting` being present but empty is a real request: it is how 分类 asks
   * for the corpus-wide counts it prints before anything is narrowed. That is
   * one 44 KB file and not a single column. Passing nothing at all is the
   * unfiltered stream asking, and that costs nothing.
   *
   * Resolves immediately when there is nothing to do, so a caller can await it
   * unconditionally.
   */
  async function ready(filter: Filter, counting?: Axis[]): Promise<void> {
    const wanted = new Set<Axis>(counting ?? [])
    for (const { key } of AXES) if (filter[key]) wanted.add(key)
    if (!wanted.size && counting === undefined) return
    await loadFacets()
    await Promise.all([...wanted].map(loadColumn))
  }

  return { n: CORPUS_N, has, pool, facet, poem, ready }
}
