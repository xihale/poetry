<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { data } = await usePoems()
const view = usePoemView(data, id)
const { mark } = useLastRead()

if (!view.value.poem) {
  throw createError({ statusCode: 404, message: '没有这一篇', fatal: true })
}

const { poem, list, prev, next } = view.value

useSeoMeta({
  title: () => `${poem.title} · 诗存`,
  description: () => poem.excerpt,
})

// Entrance: the title arrives first, the verses follow in reading order.
const entered = useState('entered-poem', () => false)
const play = ref(false)
const progress = ref(0)
let raf = 0

onMounted(() => {
  mark(poem.id)
  if (!entered.value) {
    play.value = true
    entered.value = true
  }

  // Reading progress: a hairline at the top of the viewport, driven by scroll.
  const update = () => {
    raf = 0
    const doc = document.documentElement
    const max = doc.scrollHeight - doc.clientHeight
    progress.value = max > 0 ? Math.min(1, Math.max(0, doc.scrollTop / max)) : 0
  }
  const onScroll = () => {
    if (!raf) raf = requestAnimationFrame(update)
  }
  update()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
  onBeforeUnmount(() => {
    window.removeEventListener('scroll', onScroll)
    window.removeEventListener('resize', onScroll)
    if (raf) cancelAnimationFrame(raf)
  })
})

function verseDelay(i: number) {
  return play.value ? { animationDelay: `${180 + Math.min(i, 14) * 45}ms` } : undefined
}
</script>

<template>
  <div v-if="poem" class="page">
    <div class="progress" aria-hidden="true">
      <i :style="{ transform: `scaleX(${progress})` }" />
    </div>

    <Masthead :count="list.length" />

    <nav class="crumb" aria-label="面包屑">
      <NuxtLink class="crumb__back" to="/">
        <span aria-hidden="true">←</span>
        返回目录
      </NuxtLink>
      <span class="crumb__pos">第 {{ poem.no }} 篇 · 共 {{ list.length }} 篇</span>
    </nav>

    <article class="poem">
      <aside class="poem__margin" aria-hidden="true">
        <span class="poem__margin-no">{{ poem.no }}</span>
        <span class="poem__margin-rule" />
        <span class="poem__margin-label">诗存</span>
      </aside>

      <div class="poem__column">
        <header class="poem__head" :class="{ enter: play }">
          <h1 class="poem__title">{{ poem.title }}</h1>
          <div class="poem__meta">
            <span>{{ poem.extra || '无日期' }}</span>
            <span class="poem__dot" aria-hidden="true">·</span>
            <span>{{ poem.chars }} 字</span>
          </div>
        </header>

        <div class="poem__body">
          <p
            v-for="(line, i) in poem.lines"
            :key="i"
            class="verse"
            :class="{ 'verse--gap': !line.trim(), enter: play && !!line.trim() }"
            :style="verseDelay(i)"
          >{{ line }}</p>
        </div>

        <footer class="poem__foot">
          <NuxtLink v-if="prev" class="step step--prev" :to="`/${prev.no}`">
            <span class="step__dir" aria-hidden="true">←</span>
            <span class="step__label">较新一篇 · {{ prev.no }}</span>
            <span class="step__title">{{ prev.title }}</span>
          </NuxtLink>
          <span v-else class="step step--empty">已是最新一篇</span>

          <NuxtLink v-if="next" class="step step--next" :to="`/${next.no}`">
            <span class="step__label">较早一篇 · {{ next.no }}</span>
            <span class="step__title">{{ next.title }}</span>
            <span class="step__dir" aria-hidden="true">→</span>
          </NuxtLink>
          <span v-else class="step step--empty">已是最早一篇</span>
        </footer>
      </div>
    </article>

    <Colophon :count="list.length" :total="list.reduce((s, p) => s + p.chars, 0)" />
  </div>
</template>

<style scoped>
.progress {
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 20;
  height: 2px;
}

.progress i {
  display: block;
  height: 100%;
  background: var(--rub);
  transform-origin: 0 50%;
  transform: scaleX(0);
}

.crumb {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 0;
  font-family: var(--kai);
  font-size: 12px;
  letter-spacing: 0.22em;
  color: var(--ink-soft);
}

.crumb__back {
  display: inline-flex;
  align-items: baseline;
  gap: 0.6em;
  padding: 6px 0;
  border-bottom: 1px solid transparent;
  transition: color 0.18s var(--ease), border-color 0.18s var(--ease);
}

.crumb__back:hover {
  color: var(--rub);
  border-color: var(--rub);
}

.crumb__back:active {
  transform: translateY(1px);
}

/* Reading page: a page column with a margin note holding the outer edge,
   so the measure stays comfortable without the column drifting off-centre. */
.poem {
  display: grid;
  grid-template-columns: auto minmax(0, 34em) 1fr;
  gap: 48px;
  padding-top: 42px;
}

.poem__column {
  grid-column: 2;
}

.poem__margin {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding-top: 6px;
  font-family: var(--kai);
  color: var(--ink-faint);
}

.poem__margin-no {
  font-size: 15px;
  letter-spacing: 0.24em;
  color: var(--rub);
  font-variant-numeric: tabular-nums;
}

.poem__margin-rule {
  width: 1px;
  height: 84px;
  background: var(--line);
}

.poem__margin-label {
  font-size: 12px;
  letter-spacing: 0.5em;
  writing-mode: vertical-rl;
  text-orientation: upright;
}

.poem__head {
  padding-bottom: 30px;
  border-bottom: 1px solid var(--line-strong);
}

.poem__title {
  font-family: var(--kai);
  font-size: clamp(38px, 5vw, 60px);
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: 0.06em;
}

.poem__meta {
  display: flex;
  gap: 0.9em;
  margin-top: 16px;
  font-family: var(--kai);
  font-size: 13px;
  letter-spacing: 0.2em;
  color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}

.poem__dot {
  color: var(--ink-faint);
}

.poem__body {
  padding: 34px 0 8px;
}

.verse {
  font-size: 17px;
  line-height: 2.15;
  letter-spacing: 0.02em;
  /* keep a line's own punctuation with it when the column is narrow */
  text-wrap: pretty;
}

.verse--gap {
  height: 0.9em;
}

.poem__foot {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 46px;
  padding-top: 20px;
  border-top: 1px solid var(--line-strong);
  font-family: var(--kai);
}

.step {
  display: flex;
  align-items: baseline;
  gap: 0.7em;
  padding: 8px 0;
  font-size: 15px;
  letter-spacing: 0.08em;
  transition: color 0.18s var(--ease);
}

.step--next {
  justify-content: flex-end;
  text-align: right;
}

.step:hover {
  color: var(--rub);
}

.step__label {
  font-size: 11px;
  letter-spacing: 0.24em;
  color: var(--ink-faint);
}

.step__title {
  font-size: 17px;
}

.step__dir {
  transition: transform 0.24s var(--ease);
}

/* press: the whole step nudges in its own direction, immediately */
.step:active {
  transform: translateY(1px);
}

.step--prev:active {
  transform: translate(1px, 1px);
}

.step--next:active {
  transform: translate(-1px, 1px);
}

.step--prev:hover .step__dir {
  transform: translateX(-5px);
}

.step--next:hover .step__dir {
  transform: translateX(5px);
}

.step--empty {
  font-size: 12px;
  letter-spacing: 0.2em;
  color: var(--ink-faint);
}

.step--empty:last-child {
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .poem {
    grid-template-columns: 1fr;
    gap: 0;
    padding-top: 30px;
  }

  .poem__column {
    grid-column: 1;
  }

  /* the margin note folds down to a single line above the title */
  .poem__margin {
    flex-direction: row;
    align-items: baseline;
    gap: 12px;
    padding: 0 0 16px;
  }

  .poem__margin-rule {
    width: 40px;
    height: 1px;
  }

  .poem__margin-label {
    writing-mode: horizontal-tb;
    letter-spacing: 0.4em;
  }

  .poem__body {
    max-width: none;
  }

  .verse {
    font-size: 17px;
    line-height: 2.05;
  }

  .poem__foot {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .step--next {
    justify-content: flex-start;
    text-align: left;
  }
}
</style>
