export interface Poem {
  /** Numeric id taken from the file name, e.g. content/poems/12.txt -> 12 */
  id: number
  /** Zero padded id used in routes, e.g. "12" */
  no: string
  title: string
  /** Whatever follows the title on the first line: a date ("4.18") or an author ("王守仁"). */
  extra: string
  /** Body lines, blank lines kept as stanza breaks. */
  lines: string[]
  /** First two non-empty body lines joined, for the index preview. */
  excerpt: string
  /** Count of non-whitespace body characters. */
  chars: number
}
