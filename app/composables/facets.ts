import type { Axis, Filter } from '~/types/poem'
import type { Corpus } from '~/composables/useCorpus'

/**
 * Past this many choices an axis folds, so 诗人 cannot bury the others.
 *
 * The cap is per axis, because the axes do not cost the same. 部类 runs to
 * 1,500-odd 词牌 and 卷次 to 986, and both would push everything below them off
 * the screen — so they fold hard. 时代, 体裁, 情绪, 视角 and 篇幅 each have
 * fewer values than the cap already, and folding them would hide nothing while
 * adding a click. The numbers are chosen so a folded axis is about one line at
 * the panel's width.
 */
const AXIS_CAP: Partial<Record<Axis, number>> = { cat: 12, juan: 12 }
const CAP = 18

/** Not a choice but the absence of one — never offered as a choice. */
const UNKNOWN: Partial<Record<Axis, string>> = { era: '不详' }

/** Canonical orderings, so the facets read the way a reader expects. */
export const ORDER: Partial<Record<Axis, string[]>> = {
  // 乐府诗集's own divisions first — the site is built around that book — then
  // the two 先秦 books' divisions, then the 體裁 the Tang anthologies group by.
  // 词牌 are deliberately absent: 全宋词 has 1,000-odd of them and they are not a
  // hierarchy, so they sort by name below everything listed here.
  cat: ['郊庙歌辞', '燕射歌辞', '鼓吹曲辞', '横吹曲辞', '相和歌辞', '清商曲辞',
        '舞曲歌辞', '琴曲歌辞', '杂曲歌辞', '近代曲辞', '杂歌谣辞', '新乐府辞',
        '国风', '小雅', '大雅', '周颂', '鲁颂', '商颂',
        '离骚', '九歌', '九章', '天问', '远游', '卜居', '渔父', '九辩',
        '招魂', '大招', '惜誓', '招隐士', '七谏', '哀时命', '九怀', '九叹',
        '九思',
        '五言古诗', '七言古诗', '五言律诗', '七言律诗', '五言绝句', '七言绝句'],
  era: ['先秦', '秦', '汉', '魏晋', '南北朝', '隋', '唐', '五代', '宋', '元', '明', '清',
        '英', '法', '德', '俄', '印度', '美'],
  len: ['短', '中', '长'],
  form: ['三言', '四言', '五言', '六言', '七言', '杂言', '词', '曲', '楚辞', '赋', '文',
         '新诗', '十四行诗', '散文诗', '诗'],
  lang: ['中文', 'en', 'fr', 'de', 'ru', 'ja'],
  mood: ['愁', '思', '独', '欢', '闲', '壮', '惊'],
  view: ['我', '你', '他', '谁', '天地'],
}

/**
 * 卷次 is a number, and it is printed two ways: 乐府诗集 numbers its volumes in
 * Chinese numerals (卷一, 卷二十六) and 御定全唐詩 in Arabic (卷1, 卷540). Left
 * to a string sort, 卷10 lands before 卷2 and 卷一百 before 卷二十. Both spellings
 * name the same ordinal, so both resolve into one numeric space and a 卷 list
 * reads as a table of contents instead of an alphabet.
 */
const NUMERALS = '零一二三四五六七八九'

function chineseNumber(s: string): number | null {
  const m = /^卷([零一二三四五六七八九]+)$/.exec(s)
  if (!m) return null
  const digits = m[1]!
  if (digits.length === 1) return NUMERALS.indexOf(digits)
  const [tens, ones] = digits.includes('十')
    ? digits.split('十')
    : [digits.slice(0, -1), digits.slice(-1)]
  const t = tens === '' ? 1 : NUMERALS.indexOf(tens!)
  const o = ones ? NUMERALS.indexOf(ones) : 0
  return t * 10 + o
}

const RANK: Partial<Record<Axis, (v: string) => number>> = {
  // Two books spell the same ordinal two ways, and a list that interleaves them
  // (卷一, 卷1, 卷二, 卷2 …) reads as scrambled even though it is in order. Each
  // spelling keeps its own run, in its own numeric order.
  juan: (v) => {
    const arabic = /^卷(\d+)$/.exec(v)
    if (arabic) return 1_000_000 + Number(arabic[1])
    return chineseNumber(v) ?? 2_000_000
  },
}

/** The leaves print 无名氏 for the corpus's 佚名 — one word for one poet. */
const LABEL: Partial<Record<Axis, Record<string, string>>> = {
  author: { 佚名: '无名氏' },
  lang: { 中文: '中文', en: '英文', fr: '法文', de: '德文', ru: '俄文', ja: '日文' },
}

export const axisLabel = (axis: Axis, value: string) => LABEL[axis]?.[value] ?? value

/** How many of an axis's choices are listed before it folds. */
export const axisCap = (axis: Axis) => AXIS_CAP[axis] ?? CAP

/**
 * What the folded remainder counts.
 *
 * Every other number on this panel is a number of *poems*, so a bare count next
 * to 其余 would be read as one: 其余 18 looks exactly like 恶之花 123 two chips
 * earlier, and means 18 more anthologies. The unit is the whole difference, and
 * only the axes that can fold need one.
 */
const UNIT: Partial<Record<Axis, string>> = { coll: '部', cat: '种', juan: '卷', author: '人' }

/** The unit of an axis's folded remainder, or '' for an axis that never folds. */
export const axisUnit = (axis: Axis) => UNIT[axis] ?? ''

/** Canonical order for an axis: a rank function, a fixed list, or collation. */
export function axisOrder(axis: Axis): (a: string, b: string) => number {
  const rank = RANK[axis]
  if (rank) return (a, b) => rank(a) - rank(b) || a.localeCompare(b, 'zh')
  const order = ORDER[axis]
  return (a, b) => {
    if (order) {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      if (ia !== ib) return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
    }
    return a.localeCompare(b, 'zh')
  }
}

/**
 * Every axis's choices and their live counts.
 *
 * The counting itself lives in useCorpus, over the packed index: 376,096 poems
 * are far too many to hold as objects in the browser, so nothing here ever
 * touches a poem's text — only its labels.
 */
export function axisFacet(corpus: Corpus, filter: Filter, axis: Axis) {
  const { values, counts, total } = corpus.facet(filter, axis)
  const unknown = UNKNOWN[axis]
  // Two kinds of value are not choices. 不详 is the absence of an era and is
  // never offered. '' is the absence of a 卷 or a 部类 — most poems in the canon
  // have neither — and it must not be offered either: a chip labelled with
  // nothing, carrying 430,000 poems, is not a way to read.
  const kept = values.filter((v) => v !== '' && v !== unknown)
  return {
    // Every choice that exists at all, so a list never jumps as filters change.
    values: kept,
    // How many poems each choice would leave, given the other axes.
    counts,
    // How many poems the axis itself still leaves open.
    total,
  }
}
