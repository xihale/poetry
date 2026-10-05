import type { Leaf, Poem } from '~/types/poem'

/** How many characters fit on one leaf before the poem is split. */
const LEAF_CHARS = 108

/** Split a poem into leaves, breaking at a blank line, a stanza, or a couplet. */
export function leavesOf(poem: Poem): Leaf[] {
  const lines = poem.text.split('\n')
  if (poem.chars <= LEAF_CHARS) {
    return [{ poem, lines, part: 0, parts: 1, key: `${poem.id}-0` }]
  }

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
