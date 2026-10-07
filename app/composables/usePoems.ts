import type { Leaf, Poem } from '~/types/poem'

/**
 * How much text fits on one leaf before the poem is split.
 *
 * Measured in characters, but a Latin character is about half a CJK one, so a
 * line of English gets roughly twice the budget for the same visual width.
 */
const LEAF_CJK = 64
const LEAF_LATIN = 116

const CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/

/**
 * A 赋 or 文 arrives as one unbroken line of 900-1500 characters, so splitting
 * between lines alone would leave a single wall of text on one screen. Cut at
 * the nearest clause mark instead, which is where the text already breathes.
 *
 * Latin verse has no clause marks to cut at and cannot be broken between
 * arbitrary characters — cutting 「salutation」 in half turns a poem into a
 * typo — so it is cut at the last word boundary that fits.
 */
function splitLongLine(line: string): string[] {
  const latin = !CJK.test(line)
  const budget = latin ? LEAF_LATIN : LEAF_CJK
  if (line.length <= budget) return [line]

  const out: string[] = []
  let rest = line
  while (rest.length > budget) {
    let cut = -1
    if (latin) {
      const space = rest.lastIndexOf(' ', budget)
      cut = space > budget * 0.5 ? space + 1 : budget
    } else {
      for (const m of rest.slice(0, budget + 1).matchAll(/[，。；！？、,.;!?]/g)) {
        // never cut so early that a leaf holds a stub
        if (m.index !== undefined && m.index >= budget * 0.6) cut = m.index + 1
      }
      if (cut < 0) cut = budget
    }
    out.push(rest.slice(0, cut))
    rest = rest.slice(cut)
  }
  if (rest) out.push(rest)
  return out
}

/**
 * Split a poem into leaves, breaking at a blank line, a stanza, or a couplet.
 *
 * A bilingual poem carries its two texts in parallel: `text` is the Chinese and
 * `orig` is the poem in its own language. They are split together and each leaf
 * holds the pair that belongs to it, so a long poem cannot drift out of
 * alignment halfway through.
 */
export function leavesOf(poem: Poem): Leaf[] {
  const lines = poem.text.split('\n').flatMap(splitLongLine)
  const orig = poem.orig ? poem.orig.split('\n').flatMap(splitLongLine) : null

  const groups: string[][] = []
  const origGroups: string[][] = []
  let group: string[] = []
  let origGroup: string[] = []
  let size = 0
  let at = 0

  const flush = () => {
    if (group.length) {
      groups.push(group)
      origGroups.push(origGroup)
    }
    group = []
    origGroup = []
    size = 0
  }

  for (const line of lines) {
    // a Latin line is charged what it costs on the page, not what it counts in
    // characters, so an English poem is not split twice as eagerly as a Chinese
    // one of the same width
    const n = CJK.test(line) ? line.length : Math.ceil(line.length / 1.8)
    if (size && size + n > LEAF_CJK) flush()
    group.push(line)
    if (orig) {
      // the two texts are stanza-for-stanza but not line-for-line: Tagore's
      // English runs to more lines than 郑振铎's Chinese for the same poem
      origGroup.push(...orig.slice(at, at + 1))
    }
    size += n
    at++
  }
  flush()

  if (orig && orig.length > lines.length) {
    // whatever the Chinese did not consume belongs to the last leaf
    const last = origGroups[origGroups.length - 1]
    if (last) last.push(...orig.slice(lines.length))
  }

  // a two-line tail is a widow: fold it back into the previous leaf
  if (groups.length > 1 && (groups[groups.length - 1]?.length ?? 0) < 3) {
    const tail = groups.pop()!
    const origTail = origGroups.pop() ?? []
    groups[groups.length - 1]?.push(...tail)
    origGroups[origGroups.length - 1]?.push(...origTail)
  }

  return groups.map((g, i) => ({
    poem,
    lines: g,
    orig: origGroups[i]?.length ? origGroups[i] : undefined,
    part: i,
    parts: groups.length,
    key: `${poem.id}-${i}`,
  }))
}
