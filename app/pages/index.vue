<script setup lang="ts">
import { EMPTY_FILTER, AXES } from '~/types/poem'
import type { Axis, Filter, Leaf, Poem } from '~/types/poem'

useHead({
  title: '拈一卷 · 诗单',
  meta: [{ name: 'theme-color', content: '#faf9f6' }],
})

// The poem is chosen per visit, so there is nothing for the server to render:
// the corpus is a static, cacheable file and the first poem fades in on arrival.
const { data: corpus } = await useFetch<Poem[]>('/corpus.json', { server: false })

const filter = ref<Filter>({ ...EMPTY_FILTER })
const leaves = ref<Leaf[]>([])
const panel = ref(false)
const hintGone = ref(false)
const stream = ref<HTMLElement>()

const pool = computed(() => {
  const all = corpus.value ?? []
  return all.filter((p) => {
    for (const { key } of AXES) {
      const want = filter.value[key]
      if (!want) continue
      if (key === 'mood' ? !p.mood.includes(want) : key === 'view' ? !p.view.includes(want) : p[key] !== want) {
        return false
      }
    }
    return true
  })
})

/** Drawn poems, so the same one never returns until the pool is exhausted. */
let bag: Poem[] = []
let taken: Poem[] = []

function draw(): Poem | null {
  if (!bag.length) {
    const seen = new Set(taken.map((p) => p.id))
    let rest = pool.value.filter((p) => !seen.has(p.id))
    if (!rest.length) {
      const last = taken[taken.length - 1]
      taken = []
      rest = pool.value.filter((p) => p.id !== last?.id)
    }
    bag = [...rest]
    for (let i = bag.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[bag[i], bag[j]] = [bag[j], bag[i]]
    }
  }
  const p = bag.pop() ?? null
  if (p) taken.push(p)
  return p
}

/** Keep at least `min` poems in the stream, so there is always a next one. */
function fill(min: number) {
  while (taken.length < min) {
    const poem = draw()
    if (!poem) break
    leaves.value.push(...leavesOf(poem))
  }
}

function reset() {
  bag = []
  taken = []
  leaves.value = []
  fill(2)
  stream.value?.scrollTo({ top: 0 })
}

const activeLabel = computed(() =>
  AXES.filter((a) => filter.value[a.key])
    .map((a) => `${a.label} ${filter.value[a.key]}`)
    .join('　'),
)

function toggle(axis: Axis, value: string) {
  filter.value[axis] = filter.value[axis] === value ? null : value
  reset()
}

function clearAll() {
  filter.value = { ...EMPTY_FILTER }
  reset()
}

function onScroll() {
  const el = stream.value
  if (!el) return
  if (!hintGone.value && el.scrollTop > 40) hintGone.value = true
  if (el.scrollTop + el.clientHeight > el.scrollHeight - el.clientHeight) fill(taken.length + 1)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    panel.value = false
    return
  }
  if (panel.value) return
  // the stream is its own scroll container, so the browser's default paging
  // keys never reach it — scrolling has to be driven here
  const el = stream.value
  if (!el) return
  const page = el.clientHeight
  if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') {
    e.preventDefault()
    el.scrollBy({ top: page, behavior: 'smooth' })
  } else if (e.key === 'ArrowUp' || e.key === 'PageUp') {
    e.preventDefault()
    el.scrollBy({ top: -page, behavior: 'smooth' })
  } else if (e.key === 'ArrowRight') {
    reset()
  }
}

// the corpus is fetched on the client, so the first poem is drawn on arrival
watch(corpus, () => reset(), { immediate: true })

onMounted(() => window.addEventListener('keydown', onKey))

onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div>
    <div class="filter-note">
      <span v-if="activeLabel" class="active">{{ activeLabel }}</span>
      <button @click="reset">换一首</button>
    </div>

    <div ref="stream" class="stream" @scroll.passive="onScroll">
      <PoemLeaf v-for="leaf in leaves" :key="leaf.key" :leaf="leaf" />
      <p v-if="!leaves.length && corpus" class="empty">此卷无诗</p>
    </div>

    <p class="edge hint" :class="{ gone: hintGone || leaves.length < 2 }">
      向下滑动
    </p>

    <button class="edge facets-btn" @click="panel = true">分类</button>

    <Transition name="panel">
      <Facets
        v-if="panel"
        :pool="corpus ?? []"
        :filter="filter"
        @toggle="toggle"
        @clear="clearAll"
        @close="panel = false"
      />
    </Transition>
  </div>
</template>

<style scoped>
.empty {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ghost);
  letter-spacing: 0.5em;
  text-indent: 0.5em;
}
</style>
