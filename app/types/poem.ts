export interface Poem {
  id: number
  title: string
  era: string
  form: string
  mood: string[]
  view: string[]
  /** CJK character count, used for the length band and for splitting leaves. */
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
export type Axis = 'era' | 'author' | 'form' | 'mood' | 'view' | 'len'

export type Filter = Record<Axis, string | null>

export const EMPTY_FILTER: Filter = {
  era: null,
  author: null,
  form: null,
  mood: null,
  view: null,
  len: null,
}

export const AXES: { key: Axis; label: string }[] = [
  { key: 'era', label: '时代' },
  { key: 'author', label: '作者' },
  { key: 'form', label: '体裁' },
  { key: 'mood', label: '情绪' },
  { key: 'view', label: '视角' },
  { key: 'len', label: '篇幅' },
]
