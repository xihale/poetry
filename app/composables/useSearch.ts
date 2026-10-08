import type { Corpus } from '~/composables/useCorpus'
import { fetchBytes, fetchJson } from '~/utils/bytes'
import { CORPUS_BUILD } from '~/corpus-meta'

/**
 * Search over the whole corpus, from a bigram index that is fetched on demand.
 *
 * The problem: 125,314 poems is 21 MB of text and the browser cannot hold it,
 * let alone scan it — but a poetry site's reason to have search at all is the
 * half-remembered line, and 「明月几时有」 is a *substring* of the verse. No
 * amount of indexing the labels answers that.
 *
 * The solution is an index of 2-grams, sharded by a hash of the bigram.
 * A query is split into its own bigrams, only those shards are fetched, their
 * posting lists are intersected to get candidates, and each candidate is then
 * confirmed against its actual text. Two properties matter:
 *
 *   - it is exact. A 2-gram index answers any substring query without a word
 *     segmenter, a dictionary, or a guess about where a word ends.
 *   - it is cheap to ask. Six characters is five shards — tens of kilobytes,
 *     cached forever — instead of the 28 MB whole.
 *
 * Everything is normalised the same way on both sides (see `normalise`), so the
 * index and the query agree, and a phrase that spans a line break still matches.
 */

export interface Hit {
  id: number
  title: string
  author: string
  coll: string
  /** the line the query was found on, as printed */
  line: string
  /** the matched span within `line`, for marking it */
  mark: [number, number]
  /** the match is in the title rather than the verse */
  inTitle: boolean
}

/** What the index holds: CJK, Latin letters and digits. Punctuation and spaces
 *  are dropped, so 「明月，几时有」 and 「明月几时有」 are the same query. */
const INDEXED = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff0-9a-z]/

export function normalise(s: string): string {
  let out = ''
  for (const ch of s.toLowerCase()) if (INDEXED.test(ch)) out += ch
  return out
}

function pairs(s: string): string[] {
  const out: string[] = []
  for (let i = 0; i < s.length - 1; i++) out.push(s.slice(i, i + 2))
  return out
}

/** The FNV-1a shard a bigram lives in. Must match scripts/build-search.py. */
function shardOf(bigram: string): number {
  let h = 0x811c9dc5
  for (const byte of new TextEncoder().encode(bigram)) {
    h ^= byte
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h % shards
}

let shards = 8192

function readVarint(buf: Uint8Array, pos: number): [number, number] {
  let value = 0
  let shift = 0
  let byte: number
  do {
    byte = buf[pos++]!
    value += (byte & 0x7f) * 2 ** shift
    shift += 7
  } while (byte & 0x80)
  return [value, pos]
}

/** One shard, after fetchBytes has gunzipped it: length-prefixed bigram, count,
 *  then delta-encoded ids. */
function parseShard(buf: Uint8Array): Map<string, Uint32Array> {
  const out = new Map<string, Uint32Array>()
  const decoder = new TextDecoder()
  let pos = 0
  while (pos < buf.length) {
    const [len, p1] = readVarint(buf, pos)
    const bigram = decoder.decode(buf.subarray(p1, p1 + len))
    const [count, p2] = readVarint(buf, p1 + len)
    const ids = new Uint32Array(count)
    let prev = 0
    let at = p2
    for (let i = 0; i < count; i++) {
      const [delta, next] = readVarint(buf, at)
      prev += delta
      ids[i] = prev
      at = next
    }
    out.set(bigram, ids)
    pos = at
  }
  return out
}

interface SearchIndex {
  shards: number
  bigrams: number
  postings: number
  poems: number
  /** The corpus the index was built from; see app/corpus-meta.ts. */
  corpus: string
}

let ready: Promise<void> | null = null
const loaded = new Map<number, Map<string, Uint32Array>>()
const fetching = new Map<number, Promise<Map<string, Uint32Array>>>()

/**
 * The index's load, shared by every search and retried after a failure.
 *
 * A caller awaits the promise this returns, never the module's record of it: a
 * failure clears that record so the next search asks again, and a caller that
 * awaited the record afterwards would await `null` — resolving immediately and
 * searching against the shard count of a load that never happened. That is not
 * hypothetical: it made a refusal to load look like an answer.
 */
function index(): Promise<void> {
  if (ready) return ready
  let flight: Promise<void>
  flight = fetchJson<SearchIndex>('/corpus/search/meta.json')
    .then((meta) => {
      // The index is built from the chunks, and scripts/build-search.py copies
      // the stamp the chunks carry into this file. A search answered from a
      // different corpus is the one failure a reader cannot see — it says
      // 「没有这一句」 about a line that is on the site — so the stamp is checked
      // before the index is used at all.
      if (meta.corpus !== CORPUS_BUILD) {
        throw new Error(
          `the search index is stamped ${meta.corpus}, the corpus is ${CORPUS_BUILD}`)
      }
      shards = meta.shards
    })
    .catch((err) => {
      if (ready === flight) ready = null
      throw err
    })
  ready = flight
  return flight
}

async function shard(n: number): Promise<Map<string, Uint32Array>> {
  const hit = loaded.get(n)
  if (hit) return hit
  let flight = fetching.get(n)
  if (!flight) {
    const url = `/corpus/search/${String(n).padStart(4, '0')}.bin.gz`
    flight = fetchBytes(url)
      .then((bytes) => {
        const parsed = parseShard(bytes)
        loaded.set(n, parsed)
        return parsed
      })
      // a shard that failed to arrive is forgotten rather than cached: one bad
      // fetch should not be this query's answer for the life of the page
      .finally(() => fetching.delete(n))
    fetching.set(n, flight)
  }
  return flight
}

/** The intersection of the posting lists, smallest first. */
function intersect(lists: Uint32Array[]): Uint32Array {
  if (!lists.length) return new Uint32Array(0)
  lists.sort((a, b) => a.length - b.length)
  let current = lists[0]!
  for (let i = 1; i < lists.length && current.length; i++) {
    const other = lists[i]!
    const out: number[] = []
    let a = 0
    let b = 0
    while (a < current.length && b < other.length) {
      const x = current[a]!
      const y = other[b]!
      if (x === y) {
        out.push(x)
        a++
        b++
      } else if (x < y) a++
      else b++
    }
    current = Uint32Array.from(out)
  }
  return current
}

/**
 * Every bigram of the query and its posting list, `undefined` when the corpus
 * holds no such pair. The terms are distinct: a repeated bigram says the same
 * thing twice, and the relaxed answer below would count that twice.
 */
async function postingsOf(query: string): Promise<{
  terms: string[]
  lists: (Uint32Array | undefined)[]
}> {
  await index()
  const terms = [...new Set(pairs(normalise(query)))]
  const where: number[] = []
  const need = new Set<number>()
  for (const term of terms) {
    const n = shardOf(term)
    where.push(n)
    need.add(n)
  }
  const numbers = [...need]
  const parts = await Promise.all(numbers.map(shard))
  const tables = new Map<number, Map<string, Uint32Array>>()
  numbers.forEach((n, i) => tables.set(n, parts[i]!))
  return { terms, lists: terms.map((t, i) => tables.get(where[i]!)?.get(t)) }
}

/**
 * The relaxed candidate set: every poem sharing at least two of the query's
 * bigrams, most-shared first. One shared bigram is nothing — 「人间」 alone
 * would drag in thousands — two is the least that still says the poem and the
 * query are about the same words. The lists are the ones the exact round
 * already fetched; this costs a scan of the postings, not another request.
 */
function nearCandidates(lists: (Uint32Array | undefined)[]): { id: number; cov: number }[] {
  const cov = new Map<number, number>()
  for (const list of lists) {
    if (!list) continue
    for (const id of list) cov.set(id, (cov.get(id) ?? 0) + 1)
  }
  const out: { id: number; cov: number }[] = []
  for (const [id, n] of cov) if (n >= 2) out.push({ id, cov: n })
  out.sort((a, b) => b.cov - a.cov || a.id - b.id)
  return out
}

/** Where the query lands in one poem without landing exactly. */
interface Near {
  line: string
  mark: [number, number]
  /** how many of the query's bigrams the best line carries */
  score: number
  /** how many of the query's characters the best line carries */
  overlap: number
  inTitle: boolean
}

/**
 * The line of a poem that carries the most of the query's bigrams, with each
 * bigram's printed span merged into runs and the longest run kept as the mark.
 *
 * The index cannot repair a wrong character, and this does not try — it counts
 * what did arrive. 「兰陵王·凤啸咽」 keeps two of its four bigrams on every
 * 兰陵王 in the corpus; what separates the right one is the second count: of
 * thirty-odd siblings, the title that still shares 凤 and 咽 with the query is
 * the one the reader meant.
 */
function nearOf(poem: { title: string; text: string }, terms: string[],
                needle: string): Near | null {
  let best: Near | null = null
  const consider = (raw: string, inTitle: boolean) => {
    const target = normalise(raw)
    const spans: [number, number][] = []
    for (const term of terms) {
      const at = target.indexOf(term)
      if (at < 0) continue
      // the normalised offset back onto the printed string, as the exact
      // search maps it
      let seen = 0
      let start = -1
      let end = raw.length
      for (let i = 0; i < raw.length; i++) {
        if (INDEXED.test(raw[i]!.toLowerCase())) {
          if (seen === at) start = i
          if (seen === at + term.length - 1) { end = i + 1; break }
          seen++
        }
      }
      if (start < 0) continue
      spans.push([start, end])
    }
    if (!spans.length) return
    spans.sort((a, b) => a[0]! - b[0]!)
    const runs: [number, number][] = []
    for (const s of spans) {
      const last = runs[runs.length - 1]
      if (last && s[0]! <= last[1]!) last[1] = Math.max(last[1]!, s[1]!)
      else runs.push([s[0]!, s[1]!])
    }
    const mark = runs.reduce((a, b) => (b[1] - b[0] > a[1] - a[0] ? b : a))
    const pool = new Map<string, number>()
    for (const ch of target) pool.set(ch, (pool.get(ch) ?? 0) + 1)
    let overlap = 0
    for (const ch of needle) {
      const left = pool.get(ch) ?? 0
      if (left) { overlap++; pool.set(ch, left - 1) }
    }
    if (!best || spans.length > best.score
        || (spans.length === best.score && overlap > best.overlap)) {
      best = { line: raw, mark, score: spans.length, overlap, inTitle }
    }
  }
  consider(poem.title, true)
  for (const line of poem.text.split('\n')) consider(line, false)
  return best
}

export interface Found {
  hits: Hit[]
  /**
   * Whether every candidate was confirmed against its text. The index only says
   * "these poems contain all of the query's bigrams", which is not the same as
   * containing the query — so the count a reader is shown has to be the number
   * of *confirmed* hits, and when the scan stopped early the answer is a prefix
   * rather than a total.
   */
  complete: boolean
  /** how many candidates the index offered before confirmation */
  candidates: number
}

export interface Search {
  run(query: string, limit?: number): Promise<Found>
}

export function useSearch(corpus: Corpus): Search {
  // Started here rather than at the first query: opening the panel and typing
  // should not each wait for a round trip. A failure is not swallowed — `run`
  // awaits the same thing and reports it — this only keeps an eager start from
  // being an unhandled rejection.
  void index().catch(() => {})

  async function candidatesOf(query: string): Promise<Uint32Array> {
    const { terms, lists } = await postingsOf(query)
    if (!terms.length) return new Uint32Array(0)

    const ok: Uint32Array[] = []
    for (const list of lists) {
      // a bigram nothing contains means nothing matches; the intersection is empty
      if (!list) return new Uint32Array(0)
      ok.push(list)
    }
    return intersect(ok)
  }

  /**
   * Confirm each candidate against its real text and keep the ones that
   * actually contain the phrase.
   *
   * The index says "these poems contain every bigram of the query"; that is not
   * the same as containing the query — 「明月」 and 「月几」 both appearing does
   * not make 「明月几」. Confirming is what makes the answer exact rather than
   * merely plausible, and it is nearly free because a poem's text is already a
   * cached chunk fetch.
   */
  async function run(query: string, limit = 80): Promise<Found> {
    const needle = normalise(query)
    if (needle.length < 2) return { hits: [], complete: true, candidates: 0 }
    const ids = await candidatesOf(query)
    const hits: Hit[] = []
    let scanned = 0

    // 24, not the couple hundred it used to be: the loop stops the moment the
    // limit is full, so a bigger batch only buys the text of poems the reader
    // will never be shown. A small batch reaches the same hits and reads less.
    const batch = 24
    for (let at = 0; at < ids.length && hits.length < limit; at += batch) {
      scanned = Math.min(ids.length, at + batch)
      const batchIds = [...ids.slice(at, at + batch)]
      const poems = await Promise.all(batchIds.map((id) => corpus.poem(id)))
      for (const poem of poems) {
        const title = normalise(poem.title)
        const body = normalise(poem.text)
        const inTitle = title.includes(needle)
        if (!inTitle && !body.includes(needle)) continue

        // find the printed line the query sits on, so the result shows the
        // reader the line they half-remembered rather than the whole poem
        let line = poem.title
        let mark: [number, number] = [0, 0]
        const search = (raw: string) => {
          const target = normalise(raw)
          const at = target.indexOf(needle)
          if (at < 0) return false
          // map the normalised offset back onto the printed string
          let seen = 0
          let start = 0
          let end = raw.length
          for (let i = 0; i < raw.length; i++) {
            if (INDEXED.test(raw[i]!.toLowerCase())) {
              if (seen === at) start = i
              if (seen === at + needle.length - 1) { end = i + 1; break }
              seen++
            }
          }
          mark = [start, end]
          return true
        }
        if (!inTitle) {
          const found = poem.text.split('\n').find((l) => search(l))
          if (found === undefined) continue
          line = found
        } else {
          search(poem.title)
        }

        hits.push({ id: poem.id, title: poem.title, author: poem.author,
                    coll: poem.coll, line, mark, inTitle })
        if (hits.length >= limit) break
      }
    }

    // A hit in the title is what the reader named, not just where the words
    // appear; after that a short poem is likelier to be the one they meant.
    hits.sort((a, b) => Number(b.inTitle) - Number(a.inTitle) || a.id - b.id)
    if (hits.length) {
      return { hits, complete: scanned >= ids.length, candidates: ids.length }
    }
    return near(needle, limit)
  }

  /**
   * The second chance, after the exact answer came back empty.
   *
   * Nothing in the corpus holds the phrase, so the exact contract is
   * unmeetable — but 「兰陵王·凤啸咽」 typed for 「兰陵王·凤箫咽」 is one wrong
   * character from the poem the reader wants, and 「没有这一句」 would send them
   * away. The index cannot repair the character and this does not try: the
   * query's bigrams that *did* land still tie candidates to the query. Poems
   * sharing at least two of them are confirmed against their text like any
   * exact candidate, ranked by shared bigrams, then by how much of the query
   * their best line carries, then title hits first. The mark is the longest
   * run that actually matched, so the list shows what arrived, not what was
   * hoped for — nothing here pretends the query is on the page.
   */
  async function near(needle: string, limit: number): Promise<Found> {
    const { terms, lists } = await postingsOf(needle)
    const cands = terms.length >= 2 ? nearCandidates(lists) : []
    const hits: (Hit & { cov: number; overlap: number })[] = []
    let scanned = 0

    const batch = 24
    for (let at = 0; at < cands.length && hits.length < limit; at += batch) {
      scanned = Math.min(cands.length, at + batch)
      const slice = cands.slice(at, at + batch)
      const poems = await Promise.all(slice.map((c) => corpus.poem(c.id)))
      poems.forEach((poem, i) => {
        const found = nearOf(poem, terms, needle)
        if (!found || found.score < 2) return
        hits.push({ id: poem.id, title: poem.title, author: poem.author,
                    coll: poem.coll, line: found.line, mark: found.mark,
                    inTitle: found.inTitle, cov: slice[i]!.cov,
                    overlap: found.overlap })
      })
    }

    hits.sort((a, b) => b.cov - a.cov || b.overlap - a.overlap
                      || Number(b.inTitle) - Number(a.inTitle) || a.id - b.id)
    return { hits, complete: scanned >= cands.length, candidates: cands.length }
  }

  return { run }
}
