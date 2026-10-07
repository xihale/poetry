import { AXES, EMPTY_FILTER } from '~/types/poem'
import type { Axis, Filter } from '~/types/poem'

/**
 * The filter as a path: `#诗集=宋诗选&作者=陆游`.
 *
 * A narrowed collection is a place, so it gets an address. Three things follow
 * from that and all three are the point of doing it: the reader can share a
 * 卷 they have narrowed to, reload it without losing it, and — because the hash
 * goes into the browser's history — use the back button to step out of a filter
 * they stepped into, which is the way a reader expects to undo one.
 *
 * The hash and not the path or the query string: this is a static build with no
 * server, and a hash never asks one for anything. A path would 404 on GitHub
 * Pages and a query string would make every filter a document fetch.
 *
 * Keys are the axis names the code already uses (coll, cat, juan, era, author,
 * form, mood, view, len, lang) rather than the Chinese labels, because the hash
 * is an address and addresses are for the machine: `#author=莎士比亚` survives
 * a rename of the label, and it is what a reader sees in the URL bar next to a
 * bookmarked 李白 — short, and no percent-encoding for the common case.
 */
export const HASH_KEY: Record<Axis, string> = {
  coll: 'coll',
  cat: 'cat',
  juan: 'juan',
  era: 'era',
  author: 'author',
  form: 'form',
  lang: 'lang',
  mood: 'mood',
  view: 'view',
  len: 'len',
}

const BY_KEY = new Map(Object.entries(HASH_KEY).map(([axis, key]) => [key, axis as Axis]))

/**
 * The filter as a hash fragment, in the panel's own axis order so the same
 * filter always produces the same address. `''` when nothing is filtered —
 * the unfiltered collection is the page itself and needs no fragment.
 */
export function toHash(filter: Filter): string {
  const parts: string[] = []
  for (const { key } of AXES) {
    const value = filter[key]
    if (value) parts.push(`${HASH_KEY[key]}=${encodeURIComponent(value)}`)
  }
  return parts.join('&')
}

/**
 * A hash fragment as a filter.
 *
 * Anything unrecognised is dropped rather than rejected: the axis names and the
 * values in a shared link outlive the corpus they were written against, and a
 * link that names a poet the corpus no longer carries should open the poems
 * that are still there, not an error. An empty result and a broken link are
 * different things, and only one of them is worth a message.
 */
export function fromHash(hash: string): Filter {
  const filter: Filter = { ...EMPTY_FILTER }
  const body = hash.replace(/^#/, '')
  if (!body) return filter
  for (const pair of body.split('&')) {
    const at = pair.indexOf('=')
    if (at < 0) continue
    let axis: Axis | undefined
    let value: string
    try {
      axis = BY_KEY.get(decodeURIComponent(pair.slice(0, at)))
      value = decodeURIComponent(pair.slice(at + 1))
    } catch {
      // a half-typed escape (`#author=%E4`) is not a filter: it is a link that
      // was cut off, and decoding it throws. Skipping the pair is the same
      // promise the rest of this function makes — a link the corpus cannot
      // answer opens what is there rather than nothing at all.
      continue
    }
    if (axis && value) filter[axis] = value
  }
  return filter
}

/** Whether two filters name the same place, so a hash write can be skipped. */
export function sameFilter(a: Filter, b: Filter): boolean {
  return AXES.every(({ key }) => a[key] === b[key])
}

/**
 * A filter with the values the corpus does not carry dropped.
 *
 * `fromHash` cannot keep the promise it makes on its own: it runs before the
 * corpus is loaded, and the values a corpus carries arrive with it. So the axes
 * are dropped there and the values are dropped here, once there are
 * dictionaries to test them against. Both are the same promise — a link that
 * names a poet who is gone opens the poems that are still there, rather than a
 * collection that cannot be answered.
 */
export function prune(filter: Filter, has: (axis: Axis, value: string) => boolean): Filter {
  const kept: Filter = { ...EMPTY_FILTER }
  for (const { key } of AXES) {
    const value = filter[key]
    if (value && has(key, value)) kept[key] = value
  }
  return sameFilter(filter, kept) ? filter : kept
}

/** Whether a filter names anywhere at all. */
export function isFiltered(filter: Filter): boolean {
  return AXES.some(({ key }) => filter[key])
}
