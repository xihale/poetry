import type { Leaf, Poem } from '~/types/poem'

/** How many characters fit on one leaf before the poem is split. */
const LEAF_CHARS = 108

/**
 * A 赋 or 文 arrives as one unbroken line of 900-1500 characters, so splitting
 * between lines alone would leave a single wall of text on one screen. Cut at
 * the nearest clause mark instead, which is where the text already breathes.
 */
function splitLongLine(line: string): string[] {
  if (line.length <= LEAF_CHARS) return [line]
  const out: string[] = []
  let rest = line
  while (rest.length > LEAF_CHARS) {
    let cut = -1
    for (const m of rest.slice(0, LEAF_CHARS + 1).matchAll(/[，。；！？、]/g)) {
      // never cut so early that a leaf holds a stub
      if (m.index !== undefined && m.index >= LEAF_CHARS * 0.6) cut = m.index + 1
    }
    if (cut < 0) cut = LEAF_CHARS
    out.push(rest.slice(0, cut))
    rest = rest.slice(cut)
  }
  if (rest) out.push(rest)
  return out
}

/** Split a poem into leaves, breaking at a blank line, a stanza, or a couplet. */
export function leavesOf(poem: Poem): Leaf[] {
  const lines = poem.text.split('\n').flatMap(splitLongLine)

  const groups: string[][] = []
  let group: string[] = []
  let size = 0

  const flush = () => {
    if (group.length) groups.push(group)
    group = []
    size = 0
  }

  for (const line of lines) {
    const n = line.length
    if (size && size + n > LEAF_CHARS) flush()
    group.push(line)
    size += n
  }
  flush()

  // a two-line tail is a widow: fold it back into the previous leaf
  if (groups.length > 1 && groups[groups.length - 1].length < 3) {
    const tail = groups.pop()!
    groups[groups.length - 1].push(...tail)
  }

  return groups.map((g, i) => ({
    poem,
    lines: g,
    part: i,
    parts: groups.length,
    key: `${poem.id}-${i}`,
  }))
}
