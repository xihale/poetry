import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

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
  /** First non-empty body lines joined, for the index preview. */
  excerpt: string
  /** Count of non-whitespace body characters. */
  chars: number
}

const POEM_DIR = 'content/poems'

function parse(id: number, text: string): Poem {
  const nl = text.indexOf('\n')
  const head = (nl === -1 ? text : text.slice(0, nl)).trim()
  const [rawTitle, rawExtra = ''] = head.split('|')

  const body = nl === -1 ? '' : text.slice(nl + 1)
  const lines = body.replace(/\r/g, '').split('\n').map((l) => l.trimEnd())
  while (lines.length && !lines[0].trim()) lines.shift()
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop()

  const nonEmpty = lines.filter((l) => l.trim())

  return {
    id,
    no: String(id).padStart(2, '0'),
    title: (rawTitle || '无题').trim(),
    extra: rawExtra.trim(),
    lines,
    excerpt: nonEmpty.slice(0, 2).join(''),
    chars: nonEmpty.join('').replace(/\s/g, '').length,
  }
}

/**
 * Reads content/poems at build time and returns every poem, newest first.
 * Server only: called from nuxt.config for prerendering and from the page
 * payload builder, never from client code.
 */
export function loadPoems(): Poem[] {
  const dir = join(process.cwd(), POEM_DIR)
  return readdirSync(dir)
    .filter((f) => f.endsWith('.txt'))
    .map((f) => parse(Number.parseInt(f, 10), readFileSync(join(dir, f), 'utf8')))
    .filter((p) => Number.isFinite(p.id))
    .sort((a, b) => b.id - a.id)
}
