export interface Poem {
  id: number
  title: string
  author: string
  era: string
  /** The anthology the poem is printed in, e.g. 乐府诗集. */
  coll: string
  /** The anthology's own division, e.g. 相和歌辞. */
  cat: string
  /** The juan it sits in, e.g. 卷二十六. */
  juan: string
  /** The juan's own label, e.g. 卷二十六·相和歌辞一. */
  chapter: string
  /** The compiler's 解题, quoting the sources behind the piece. */
  note: string
  form: string
  /** 短 / 中 / 长, by character count. */
  len: string
  mood: string[]
  view: string[]
  /** Character count, used for the length band and for splitting leaves. */
  chars: number
  /** The verse itself, one 句 to a line. */
  text: string
  /** The language of the text on the page: 中文, or en/de/fr for an original. */
  lang: string
  /** The language of `orig`, when the leaf prints a translation under it. */
  olang?: string
  /**
   * The poem in its own language, when the leaf prints a Chinese text beside
   * it. Only the bilingual books carry one: 飞鸟集 is Tagore's English with
   * 郑振铎's Chinese, and the originals-only books put the original in `text`.
   */
  orig?: string
}

/** One screen's worth of a poem. A short poem is a single leaf; 焦仲卿妻 is many. */
export interface Leaf {
  poem: Poem
  lines: string[]
  /** the same verse in the poem's own language, when it is not Chinese */
  orig?: string[]
  part: number
  parts: number
  key: string
}

/**
 * Where a chooser hangs, in viewport coordinates. It is measured from the label
 * that opened it, but it drops below the leaf's whole apparatus and stays clear
 * of the verse: the poem is the context for the choice, so it must stay on
 * screen while the choice is being made.
 */
export interface Anchor {
  left: number
  top: number
  /** the foot of the apparatus — nothing may be cut through above this */
  drop: number
  verse: { left: number; right: number } | null
}

export type Axis =
  | 'coll' | 'cat' | 'juan' | 'era' | 'author'
  | 'form' | 'mood' | 'view' | 'len' | 'lang'

export type Filter = Record<Axis, string | null>

export const EMPTY_FILTER: Filter = {
  coll: null,
  cat: null,
  juan: null,
  era: null,
  author: null,
  form: null,
  mood: null,
  view: null,
  len: null,
  lang: null,
}

/** Outer to inner: the anthology, its divisions, then how the poem reads. */
export const AXES: { key: Axis; label: string }[] = [
  { key: 'coll', label: '诗集' },
  { key: 'cat', label: '部类' },
  { key: 'juan', label: '卷次' },
  { key: 'era', label: '时代' },
  { key: 'author', label: '作者' },
  { key: 'form', label: '体裁' },
  { key: 'lang', label: '语言' },
  { key: 'mood', label: '情绪' },
  { key: 'view', label: '视角' },
  { key: 'len', label: '篇幅' },
]

/**
 * A label the corpus stores per poem. `chapter` is printed on the leaf but is
 * not a facet: 卷二十六·相和歌辞一 is the 卷's own caption, not a choice.
 */
export type Label = Axis | 'chapter' 

const DIGITS = '零一二三四五六七八九'

/**
 * 乐府诗集 numbers its hundred 卷 in Chinese numerals, and pinyin collation
 * orders those wrongly — 卷一百 (yībai) would sort second, 卷二十 (ershi) third.
 * The axis is ordered by number instead.
 */
export function juanName(n: number): string {
  if (n === 100) return '卷一百'
  const tens = Math.floor(n / 10)
  const ones = n % 10
  return `卷${tens ? (tens === 1 ? '' : DIGITS[tens]) + '十' : ''}${ones ? DIGITS[ones] : ''}`
}

/** The canonical 卷次 order, so the facet adds up as a book rather than a list. */
export const JUAN_ORDER: string[] = Array.from({ length: 100 }, (_, i) => juanName(i + 1))

/** 御定全唐詩's 900 卷, in the same shape. */
export const JUAN_900: string[] = Array.from({ length: 900 }, (_, i) => `卷${i + 1}`)
