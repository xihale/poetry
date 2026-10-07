<script setup lang="ts">
import { AXES } from '~/types/poem'
import type { Anchor, Axis, Filter } from '~/types/poem'
import type { Corpus } from '~/composables/useCorpus'
import { axisFacet, axisLabel, axisUnit } from '~/composables/facets'

const props = defineProps<{
  axis: Axis
  anchor: Anchor
  corpus: Corpus
  filter: Filter
}>()

const emit = defineEmits<{
  (e: 'pick', value: string | null): void
  (e: 'more'): void
  (e: 'close'): void
}>()

/** An author list runs to 559 names. A reader looking for another name wants
 *  the names first; the rest are one click away in 分类. */
const SHOWN: Partial<Record<Axis, number>> = { author: 30 }

const facet = computed(() => axisFacet(props.corpus, props.filter, props.axis))

const listed = computed(() => {
  const rows = facet.value.values.map((value) => ({ value, n: facet.value.counts.get(value) ?? 0 }))
  const cap = SHOWN[props.axis]
  if (!cap || rows.length <= cap) return rows
  return [...rows].sort((a, b) => b.n - a.n).slice(0, cap)
})

const current = computed(() => props.filter[props.axis])

const title = computed(() => AXES.find((a) => a.key === props.axis)?.label)

const GAP = 12
const EDGE = 20
/** A list with less room than this is not worth opening. */
const MIN_ROOM = 140
/** The natural cap on the list, matching the stylesheet. */
const CAP = 26 * 16

const root = ref<HTMLElement>()
const at = ref({ left: `${props.anchor.left}px`, top: `${props.anchor.drop + GAP}px` })
const more = ref(false)

/** Is there anything below the fold? The list hides its scrollbar like the
 *  rest of the site, so the sheet has to say so itself. */
function measure() {
  const list = root.value?.querySelector<HTMLElement>('.menu__list')
  if (list) more.value = list.scrollHeight - list.scrollTop - list.clientHeight > 4
}

/**
 * Hang the sheet off the label that opened it without covering the poem: under
 * the whole apparatus, so no line is cut through, and beside the verse rather
 * than over it whenever the verse is narrow enough to leave room. The list
 * gives up height before the sheet gives up its edge, so a short window shrinks
 * the chooser instead of pushing it back over the label that opened it.
 * Re-run on resize, so a sheet opened on a wide window is not left off the edge
 * of a narrow one.
 */
function place() {
  const el = root.value
  const list = el?.querySelector<HTMLElement>('.menu__list')
  if (!el || !list) return
  const vw = window.innerWidth
  const vh = window.innerHeight
  const { left: anchorLeft, top: anchorTop, drop, verse } = props.anchor

  let left = anchorLeft
  if (verse && left < verse.right + GAP && left + el.getBoundingClientRect().width > verse.left - GAP) {
    if (verse.right + GAP + el.offsetWidth <= vw - EDGE) left = verse.right + GAP
    else if (verse.left - GAP - el.offsetWidth >= EDGE) left = verse.left - GAP - el.offsetWidth
  }
  left = Math.min(Math.max(EDGE, left), Math.max(EDGE, vw - EDGE - el.offsetWidth))

  // how much of the sheet is not the list, measured at the list's natural size
  list.style.maxHeight = ''
  const chrome = el.offsetHeight - list.offsetHeight
  const below = drop + GAP
  const roomBelow = vh - EDGE - below - chrome
  const roomAbove = anchorTop - GAP - EDGE - chrome
  const flip = roomBelow < MIN_ROOM && roomAbove > roomBelow
  const room = Math.max(MIN_ROOM, Math.min(CAP, vh * 0.6, flip ? roomAbove : roomBelow))
  list.style.maxHeight = `${Math.round(room)}px`

  const top = flip ? Math.max(EDGE, anchorTop - GAP - (chrome + room)) : below
  at.value = { left: `${Math.round(left)}px`, top: `${Math.round(top)}px` }
  measure()
}

onMounted(() => {
  place()
  window.addEventListener('resize', place)
  root.value?.focus()
})

onBeforeUnmount(() => window.removeEventListener('resize', place))
</script>

<template>
  <div
    ref="root"
    class="menu"
    :style="at"
    role="dialog"
    tabindex="-1"
    :aria-label="title"
    @keydown.esc.stop="emit('close')"
  >
    <p class="menu__lead">{{ title }}</p>

    <div class="menu__list" :class="{ 'menu__list--more': more }" @scroll.passive="measure">
      <button class="menu__row" :aria-pressed="!current" @click="emit('pick', null)">
        <span>全部</span><span class="chip__n">{{ facet.total }}</span>
      </button>
      <button
        v-for="row in listed"
        :key="row.value"
        class="menu__row"
        :class="{ 'menu__row--empty': row.n === 0 }"
        :disabled="row.n === 0"
        :aria-pressed="current === row.value"
        @click="emit('pick', row.value)"
      >
        <span>{{ axisLabel(axis, row.value) }}</span><span class="chip__n">{{ row.n }}</span>
      </button>
    </div>

    <button v-if="listed.length < facet.values.length" class="menu__more" @click="emit('more')">
      其余 {{ facet.values.length - listed.length }}{{ axisUnit(axis) }} 看分类
    </button>
  </div>
</template>
