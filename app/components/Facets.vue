<script setup lang="ts">
import { AXES } from '~/types/poem'
import type { Axis, Filter } from '~/types/poem'
import type { Corpus } from '~/composables/useCorpus'
import { ORDER, axisCap, axisFacet, axisLabel, axisOrder, axisUnit } from '~/composables/facets'

const props = defineProps<{
  corpus: Corpus
  filter: Filter
  /** Handed in when the reader asked for the full list from a leaf's label. */
  opened?: Axis | null
}>()

const emit = defineEmits<{
  (e: 'toggle', axis: Axis, value: string): void
  (e: 'clear'): void
  (e: 'close'): void
}>()

const expanded = ref<Set<Axis>>(new Set(props.opened ? [props.opened] : []))

/**
 * Every axis's choices, and which of them the panel lists.
 *
 * Two rules keep the panel navigable when a filter narrows the corpus to one
 * book. The first is that an axis the reader has *used* stays, even when the
 * filter has left it with a single value: 诗集 with one chip is not a choice,
 * but it is the reader's own choice, and removing it takes away the only
 * control that can undo it. (Everything else with one value is still dropped —
 * an axis with nothing to choose between is not a choice.)
 *
 * The second is that folding is per axis, so an axis whose values all fit is
 * listed whole. 时代 alone runs to eighteen values, and a single cap would have
 * folded it — hiding 宋 behind 其余 3 for no reason, since its list is one line.
 */
const facets = computed(() =>
  AXES.map((a) => ({ ...a, ...axisFacet(props.corpus, props.filter, a.key) }))
    .filter((a) => a.values.length > 1 || props.filter[a.key])
    .map((a) => {
      // An axis with a canonical order — 时代, 体裁, 卷次, 篇幅 — is never ranked
      // by size: 唐 before 宋 is the book's order, not a popularity vote, and a
      // 卷次 list ranked by count is no way to find 卷四十七. Only the axes that
      // have no natural order (作者, 部类) are folded down to what the current
      // pool holds most of.
      const ranked = ORDER[a.key] || a.key === 'juan'
        ? [...a.values].sort(axisOrder(a.key))
        : [...a.values].sort((x, y) => (a.counts.get(y) ?? 0) - (a.counts.get(x) ?? 0))
      const cap = axisCap(a.key)
      const open = expanded.value.has(a.key) || a.values.length <= cap
      // the reader's own value is never one of the folded-away ones
      const chosen = props.filter[a.key]
      const listed = open ? a.values : ranked.slice(0, cap)
      const values = chosen && !listed.includes(chosen) ? [chosen, ...listed] : listed
      return {
        key: a.key,
        label: a.label,
        values: values.map((v) => ({ value: v, n: a.counts.get(v) ?? 0 })),
        hidden: open ? 0 : a.values.length - listed.length,
      }
    }),
)

function more(axis: Axis) {
  expanded.value = new Set([...expanded.value, axis])
}
</script>

<template>
  <section class="panel" aria-label="分类">
    <div class="panel__inner">
      <div class="panel__axes">
        <div v-for="axis in facets" :key="axis.key" class="axis">
          <div class="axis__label">{{ axis.label }}</div>
          <div class="axis__values">
            <button
              v-for="v in axis.values"
              :key="v.value"
              class="chip"
              :class="{ 'chip--empty': v.n === 0 }"
              :disabled="v.n === 0"
              :aria-pressed="props.filter[axis.key] === v.value"
              @click="emit('toggle', axis.key, v.value)"
            >
              {{ axisLabel(axis.key, v.value) }}<span class="chip__n">{{ v.n }}</span>
            </button>
            <button v-if="axis.hidden" class="chip chip--more" @click="more(axis.key)">
              其余 {{ axis.hidden }}{{ axisUnit(axis.key) }}
            </button>
          </div>
        </div>
      </div>

      <div class="panel__foot">
        <button @click="emit('clear')">清除</button>
        <button @click="emit('close')">合卷</button>
      </div>
    </div>
  </section>
</template>
