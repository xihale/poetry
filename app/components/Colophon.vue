<script setup lang="ts">
defineProps<{
  /** Total poems in the collection. */
  count: number
  /** Total non-whitespace characters across every poem. */
  total: number
}>()

const fmt = new Intl.NumberFormat('zh-CN')
const year = new Date().getFullYear()
</script>

<template>
  <footer class="colophon">
    <div class="colophon__mark">诗&nbsp;&nbsp;存</div>
    <div class="colophon__meta">
      <span>XIHALE 个人诗稿</span>
      <span>共 {{ count }} 篇 · {{ fmt.format(total) }} 字</span>
      <span>{{ year }}</span>
    </div>
  </footer>
</template>

<style scoped>
.colophon {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  margin-top: 72px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.colophon__mark {
  font-family: var(--kai);
  font-size: 13px;
  letter-spacing: 0.34em;
}

.colophon__meta {
  display: flex;
  gap: 1.6em;
  font-family: var(--kai);
  font-size: 11px;
  letter-spacing: 0.22em;
  color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 600px) {
  .colophon {
    flex-direction: column;
    gap: 10px;
  }
}
</style>
