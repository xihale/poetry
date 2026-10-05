<script setup lang="ts">
import type { Poem } from '~/types/poem'

const props = defineProps<{
  poem: Poem
  /** True when this is the reader's stored last-read poem. */
  current?: boolean
}>()

/** "4.18" is a date; anything else (an author) is marked so the column reads true. */
const isDate = computed(() => /^\d+(\.\d+)?$/.test(props.poem.extra))
</script>
<template>
  <li>
    <NuxtLink class="row" :to="`/${poem.no}`" :data-current="current || undefined">
      <span class="row__no">{{ poem.no }}</span>
      <span class="row__title">{{ poem.title }}</span>
      <span class="row__line">{{ poem.excerpt }}</span>
      <span
        class="row__date"
        :class="{ 'row__date--author': !!poem.extra && !isDate }"
      >{{ !poem.extra ? '—' : isDate ? poem.extra : `署 ${poem.extra}` }}</span>
      <span class="sr-only">
        {{ current ? '上次读到这里，' : '' }}{{ poem.title }}，共 {{ poem.chars }} 字
      </span>
    </NuxtLink>
  </li>
</template>
