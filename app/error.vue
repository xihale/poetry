<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()

const isMissing = computed(() => props.error?.statusCode === 404)

useSeoMeta({ title: () => `${props.error?.statusCode ?? '错误'} · 诗存` })
</script>

<template>
  <div class="page">
    <header class="masthead">
      <div class="masthead__mark">
        <NuxtLink to="/">诗&nbsp;&nbsp;存</NuxtLink>
      </div>
      <div class="masthead__meta">
        <div>XIHALE 个人诗稿</div>
      </div>
    </header>

    <section class="lost">
      <div class="lost__code">{{ error?.statusCode ?? 500 }}</div>
      <h1 class="lost__title">{{ isMissing ? '没有这一篇' : '出了点问题' }}</h1>
      <p class="lost__note">
        {{ isMissing
          ? '这个编号的诗稿不在集子里，也许它还没写，也许编号记错了。'
          : '这一页没能打开。回到目录可以继续读。' }}
      </p>
      <NuxtLink class="lost__back" to="/">
        <span aria-hidden="true">←</span>
        返回目录
      </NuxtLink>
    </section>
  </div>
</template>

<style scoped>
.lost {
  padding: 96px 0 40px;
}

.lost__code {
  font-family: var(--kai);
  font-size: 13px;
  letter-spacing: 0.4em;
  color: var(--rub);
  font-variant-numeric: tabular-nums;
}

.lost__title {
  margin-top: 20px;
  font-family: var(--kai);
  font-size: clamp(40px, 6vw, 64px);
  font-weight: 400;
  line-height: 1.15;
  letter-spacing: 0.06em;
}

.lost__note {
  max-width: 30em;
  margin-top: 22px;
  font-size: 16px;
  line-height: 2;
  color: var(--ink-soft);
}

.lost__back {
  display: inline-flex;
  align-items: baseline;
  gap: 0.6em;
  margin-top: 34px;
  padding: 6px 0;
  border-bottom: 1px solid var(--line-strong);
  font-family: var(--kai);
  font-size: 14px;
  letter-spacing: 0.2em;
  transition: color 0.18s var(--ease), border-color 0.18s var(--ease);
}

.lost__back:hover {
  color: var(--rub);
  border-color: var(--rub);
}
</style>
