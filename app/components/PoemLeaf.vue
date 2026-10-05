<script setup lang="ts">
import type { Leaf } from '~/types/poem'

const props = defineProps<{ leaf: Leaf }>()

const root = ref<HTMLElement>()
const shown = ref(false)
const delay = (i: number) => 70 + Math.min(i, 14) * 42



// Each poem rises as it arrives in the viewport, so scrolling down is the
// reveal and no separate control is needed to move through the collection.
onMounted(() => {
  const el = root.value
  if (!el) return
  const io = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        shown.value = true
        io.disconnect()
      }
    },
    { threshold: 0.2 },
  )
  io.observe(el)
  onBeforeUnmount(() => io.disconnect())
})
</script>

<template>
  <article ref="root" class="leaf" :class="{ in: shown }">
    <div class="leaf__inner">
      <header v-if="props.leaf.part === 0" class="leaf__head">
        <h2 class="leaf__title">{{ props.leaf.poem.title }}</h2>
        <p class="leaf__by">
          <span v-if="props.leaf.poem.author !== '佚名'">
            {{ props.leaf.poem.author }}<span class="leaf__dot">·</span>
          </span>{{ props.leaf.poem.era }}
        </p>
      </header>
      <p v-else class="leaf__cont">
        {{ props.leaf.poem.title }}<span class="leaf__dot">·</span>{{ props.leaf.part + 1 }}/{{ props.leaf.parts }}
      </p>

      <div class="leaf__verse">
        <p
          v-for="(line, i) in props.leaf.lines"
          :key="i"
          class="leaf__line"
          :style="{ '--d': delay(i) }"
        >{{ line }}</p>
      </div>
    </div>
  </article>
</template>

<style scoped>
.leaf__cont {
  font-size: 0.72rem;
  letter-spacing: 0.36em;
  color: var(--ghost);
  margin-bottom: 2.4em;
  text-indent: 0.36em;
}

.leaf__dot {
  margin: 0 0.6em;
  color: var(--ghost);
}
</style>
