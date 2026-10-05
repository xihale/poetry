export interface Poem {
  id: number
  title: string
  author: string
  era: string
  book: string
  form: string
  mood: string[]
  view: string[]
  len: string
  /** True when the collection has a single author, so the poet name is implied. */
  solo: boolean
  chars: number
}

/** One screen's worth of a poem. A short poem is a single leaf; 离骚 is twelve. */
export interface Leaf {
  poem: Poem
  lines: string[]
  part: number
  parts: number
  key: string
}

export type Axis =
  | 'book'
  | 'era'
  | 'author'
  | 'form'
  | 'mood'
  | 'view'
  | 'len'

export type Filter = Record<Axis, string | null>

export const EMPTY_FILTER: Filter = {
  book: null,
  era: null,
  author: null,
  form: null,
  mood: null,
  view: null,
  len: null,
}

export const AXES: { key: Axis; label: string }[] = [
  { key: 'book', label: '诗集' },
  { key: 'era', label: '时代' },
  { key: 'author', label: '诗人' },
  { key: 'form', label: '体裁' },
  { key: 'mood', label: '情绪' },
  { key: 'view', label: '视角' },
  { key: 'len', label: '篇幅' },
]
