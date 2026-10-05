<script setup lang="ts">
import type { Poem } from '~/types/poem'

const { data: poems } = await usePoems()
const { lastRead, restore } = useLastRead()

const list = computed<Poem[]>(() => poems.value ?? [])
const featured = computed(() => list.value[0] ?? null)
const total = computed(() => list.value.reduce((sum, p) => sum + p.chars, 0))

useSeoMeta({
  title: '诗存 · XIHALE 个人诗稿',
  description: computed(() =>
    list.value.length
      ? `共 ${list.value.length} 篇诗稿，最新一篇《${list.value[0].title}》。`
      : '个人诗稿合集。',
  ),
})

// The entrance plays once per session: returning from a poem should not replay it.
const entered = useState('entered', () => false)
const play = ref(false)
onMounted(() => {
  restore()
  if (!entered.value) {
    play.value = true
    entered.value = true
  }
})

function delay(i: number) {
  return play.value ? { animationDelay: `${Math.min(i, 8) * 55}ms` } : undefined
}
</script>

<template>
  <div class="page">
    <Masthead :count="list.length" />
    <section v-if="featured" class="featured" :class="{ enter: play }" :style="delay(0)">
      <div class="featured__main">
        <div class="featured__index">
          <span>最新</span>
          <b>{{ featured.no }}</b>
        </div>
        <h1 class="featured__title">{{ featured.title }}</h1>
        <div class="featured__meta">
          {{ featured.extra || '无日期' }} &nbsp;&nbsp;·&nbsp;&nbsp; {{ featured.chars }} 字
        </div>
        <p class="featured__excerpt">{{ featured.excerpt }}</p>
        <NuxtLink class="featured__read" :to="`/${featured.no}`">
          通读全文
          <span aria-hidden="true">→</span>
        </NuxtLink>
      </div>
    </section>

    <div class="label" :class="{ enter: play }" :style="delay(1)">
      <h2>全 部 篇 目</h2>
      <span>共 {{ list.length }} 篇</span>
    </div>

    <ol class="rows" :class="{ enter: play }" :style="delay(2)">
      <PoemRow
        v-for="p in list"
        :key="p.id"
        :poem="p"
        :current="lastRead === p.id"
      />
    </ol>

    <Colophon :count="list.length" :total="total" />
  </div>
</template>

<style scoped>
/* The lead: one poem, full width, with its number set as a margin note on the
   left and the verse excerpt on the right. */
.featured {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, 22em);
  column-gap: 56px;
  row-gap: 20px;
  align-items: start;
  padding: 46px 0 42px;
  border-bottom: 1px solid var(--line-strong);
}

.featured__main {
  display: contents;
}

.featured__index {
  grid-column: 1;
  grid-row: 1 / span 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5em;
  padding-top: 0.4em;
  font-family: var(--kai);
  font-size: 12px;
  line-height: 1;
  letter-spacing: 0.3em;
  color: var(--rub);
}

.featured__index span {
  writing-mode: vertical-rl;
  text-orientation: upright;
  letter-spacing: 0.34em;
}

.featured__index b {
  font-weight: 400;
  font-variant-numeric: tabular-nums;
}

.featured__title {
  grid-column: 2;
  grid-row: 1;
  font-family: var(--kai);
  font-size: clamp(46px, 6.4vw, 78px);
  font-weight: 400;
  line-height: 1.04;
  letter-spacing: 0.06em;
}

.featured__meta {
  grid-column: 2;
  grid-row: 2;
  font-family: var(--kai);
  font-size: 13px;
  letter-spacing: 0.22em;
  color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}

.featured__excerpt {
  grid-column: 3;
  grid-row: 1 / span 2;
  padding-top: 0.7em;
  font-size: 15px;
  line-height: 2.05;
  color: var(--ink-soft);
}

.featured__read {
  grid-column: 2;
  grid-row: 3;
  justify-self: start;
  margin-top: 6px;
}


.featured__read {
  display: inline-flex;
  align-items: baseline;
  gap: 0.6em;
  padding: 6px 0;
  border-bottom: 1px solid var(--line-strong);
  font-family: var(--kai);
  font-size: 14px;
  letter-spacing: 0.2em;
  transition: border-color 0.18s var(--ease), color 0.18s var(--ease),
    transform 0.18s var(--ease);
}

.featured__read:active {
  transform: translateY(1px);
}

.featured__read span {
  transition: transform 0.22s var(--ease);
}

.featured__read:hover {
  border-color: var(--rub);
  color: var(--rub);
}

.featured__read:hover span {
  transform: translateX(4px);
}

@media (max-width: 900px) {
  .featured {
    grid-template-columns: auto minmax(0, 1fr);
    column-gap: 20px;
    row-gap: 16px;
    padding: 30px 0 28px;
  }

  .featured__index {
    grid-row: 1 / span 2;
  }

  .featured__title {
    font-size: clamp(38px, 11vw, 54px);
  }

  /* the excerpt moves under the title, full width */
  .featured__excerpt {
    grid-column: 1 / -1;
    grid-row: 3;
    padding-top: 0;
  }

  .featured__read {
    grid-column: 1 / -1;
    grid-row: 4;
  }
}
</style>
