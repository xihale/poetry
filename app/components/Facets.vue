<script setup lang="ts">
import { AXES } from '~/types/poem'
import type { Axis, Filter, Poem } from '~/types/poem'

const props = defineProps<{
  pool: Poem[]
  filter: Filter
}>()

const emit = defineEmits<{
  (e: 'toggle', axis: Axis, value: string): void
  (e: 'clear'): void
  (e: 'close'): void
}>()

/** Past this many choices an axis folds, so 诗人 cannot bury the others. */
const CAP = 14

const expanded = ref<Set<Axis>>(new Set())

/** Canonical orderings, so the facets read the way a reader expects. */
const ORDER: Partial<Record<Axis, string[]>> = {
  era: ['先秦', '秦', '汉', '魏晋', '南北朝', '隋', '唐', '五代', '宋', '辽',
        '金', '元', '明', '清', '近现代'],
  len: ['短', '中', '长'],
  form: ['四言', '五言', '七言', '杂言', '词', '赋', '文', '现代'],
  mood: ['愁', '思', '独', '欢', '闲', '壮', '惊'],
  view: ['我', '你', '他', '谁', '天地'],
}

function valuesOf(p: Poem, axis: Axis): string[] {
  return axis === 'mood' ? p.mood : axis === 'view' ? p.view : [p[axis] as string]
}

/** Every choice that exists at all, so the list never jumps as filters change. */
function allValues(axis: Axis): string[] {
  const seen = new Set<string>()
  for (const p of props.pool) for (const v of valuesOf(p, axis)) seen.add(v)
  const order = ORDER[axis]
  return [...seen].sort((a, b) => {
    if (order) {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
    }
    return a.localeCompare(b, 'zh')
  })
}

/**
 * Counts are faceted: every other active choice still applies, so a reader can
 * see how many poems each remaining choice would leave them. Zero means the
 * combination is empty — the choice stays visible, greyed, rather than moving.
 */
function countsFor(axis: Axis): Map<string, number> {
  const base = props.pool.filter((p) =>
    AXES.every(({ key }) => {
      if (key === axis) return true
      const want = props.filter[key]
      if (!want) return true
      return valuesOf(p, key).includes(want)
    }),
  )
  const counts = new Map<string, number>()
  for (const p of base) for (const v of valuesOf(p, axis)) counts.set(v, (counts.get(v) ?? 0) + 1)
  return counts
}

const facets = computed(() =>
  AXES.map((a) => {
    const counts = countsFor(a.key)
    const all = allValues(a.key)
    // ranked by how much of the current pool each choice holds
    const ranked = [...all].sort((x, y) => (counts.get(y) ?? 0) - (counts.get(x) ?? 0))
    const open = expanded.value.has(a.key) || ranked.length <= CAP
    return {
      ...a,
      values: (open ? ranked : ranked.slice(0, CAP)).map((v) => ({
        value: v,
        n: counts.get(v) ?? 0,
      })),
      hidden: open ? 0 : ranked.length - CAP,
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
      <p class="panel__lead">拈 一 卷</p>

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
            {{ v.value }}<span class="chip__n">{{ v.n }}</span>
          </button>
          <button v-if="axis.hidden" class="chip chip--more" @click="more(axis.key)">
            其余 {{ axis.hidden }}
          </button>
        </div>
      </div>

      <div class="panel__foot">
        <button @click="emit('clear')">清除</button>
        <button @click="emit('close')">合卷</button>
      </div>
    </div>
  </section>
</template>
