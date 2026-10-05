<script setup lang="ts">
defineProps<{
  /** Total poems in the collection. */
  count: number
}>()
</script>

<template>
  <header class="masthead">
    <div class="masthead__mark">
      <NuxtLink to="/">诗&nbsp;&nbsp;存</NuxtLink>
    </div>
    <div class="masthead__meta">
      <div>XIHALE 个人诗稿</div>
      <div><b>{{ count }}</b> 首</div>
    </div>
  </header>
</template>
