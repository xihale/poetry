<script setup lang="ts">
import type { Anchor, Axis, Filter, Leaf } from '~/types/poem'
import { axisLabel } from '~/composables/facets'

const props = defineProps<{ leaf: Leaf; filter: Filter }>()

const emit = defineEmits<{
  (e: 'pick', payload: { axis: Axis; el: HTMLElement; anchor: Anchor }): void
}>()

interface Token {
  axis: Axis
  value: string
  text: string
  /** what clicking opens, said plainly — the chooser is not a hidden filter */
  hint: string
}

/**
 * Everything printed under a title names a place in the collection, so each
 * line is also a way into it: the poet, the era, the anthology, the juan.
 * Clicking one opens its choices rather than silently narrowing the stream.
 * The value carried by a token is always the facet's own value — 乐府诗集 signs
 * its unsigned songs 佚名 and only the label says 无名氏, so a choice still
 * lands.
 */
const tokens = computed(() => {
  const { poem } = props.leaf
  const era = poem.era === '不详' ? '' : poem.era
  const by: Token[] = [
    { axis: 'author', value: poem.author, text: poem.author === '佚名' ? '无名氏' : poem.author, hint: '选其他诗人' },
  ]
  if (era) by.push({ axis: 'era', value: era, text: era, hint: '选其他时代' })
  // The language is only worth printing when it says something the line does not
  // already say. A book of English originals is labelled 英 in its era, so a
  // second label reading 英文 is noise; 飞鸟集 is the case that needs it —
  // 郑振铎's Chinese on top, Tagore's English underneath, and nothing else on
  // the line to say so.
  const shown = poem.olang ? poem.olang : (poem.era ? '' : poem.lang)
  if (shown && shown !== '中文') {
    by.push({ axis: 'lang', value: shown, text: axisLabel('lang', shown), hint: '选其他语言' })
  }

  return {
    by,
    // 卷三十七·相和歌辞十二: the juan is its own axis, the rest stays a label.
    // A source without juan numbers (诗经, 楚辞) keeps its own division there —
    // 周南, 九歌 — and a source with neither prints only the anthology.
    src: [
      { axis: 'coll' as Axis, value: poem.coll, text: poem.coll, hint: '选其他诗集' },
      ...(poem.juan
        ? [{ axis: 'juan' as Axis, value: poem.juan, text: poem.juan, hint: '选其他卷' }]
        : []),
    ],
    division: poem.chapter.includes('·')
      ? poem.chapter.split('·').slice(1).join('·')
      : poem.chapter,
  }
})

const on = (axis: Axis, value: string) => props.filter[axis] === value

const root = ref<HTMLElement>()

/**
 * The chooser needs three numbers to hang off a label without covering the
 * poem: where the label is, how far the apparatus runs, and where the verse
 * column sits.
 */
function pick(t: Token, ev: MouseEvent) {
  const leaf = root.value
  if (!leaf) return
  const el = ev.currentTarget as HTMLElement
  const token = el.getBoundingClientRect()
  const head = leaf.querySelector('.leaf__head')?.getBoundingClientRect()
  const verse = leaf.querySelector('.leaf__verse')?.getBoundingClientRect()
  emit('pick', {
    axis: t.axis,
    el,
    anchor: {
      left: token.left,
      top: token.top,
      drop: head?.bottom ?? token.bottom,
      verse: verse ? { left: verse.left, right: verse.right } : null,
    },
  })
}
</script>

<template>
  <article ref="root" class="leaf">
    <div class="leaf__inner">
      <header v-if="props.leaf.part === 0" class="leaf__head">
        <h2 class="leaf__title">{{ props.leaf.poem.title }}</h2>
        <p class="leaf__by">
          <template v-for="(t, i) in tokens.by" :key="t.axis">
            <span v-if="i" class="leaf__dot">·</span>
            <button
              class="tok"
              :aria-pressed="on(t.axis, t.value)"
              :title="t.hint"
              @click="pick(t, $event)"
            >{{ t.text }}</button>
          </template>
        </p>
        <p class="leaf__src">
          <template v-for="(t, i) in tokens.src" :key="t.axis">
            <span v-if="i" class="leaf__dot">·</span>
            <button
              class="tok"
              :aria-pressed="on(t.axis, t.value)"
              :title="t.hint"
              @click="pick(t, $event)"
            >{{ t.text }}</button>
          </template>
          <template v-if="tokens.division">
            <span class="leaf__dot">·</span>{{ tokens.division }}
          </template>
        </p>
      </header>

      <p
        v-if="props.leaf.part === 0 && props.leaf.poem.note"
        class="leaf__note"
        :class="{ 'leaf__note--line': props.leaf.poem.note.length <= 24 }"
      >{{ props.leaf.poem.note }}</p>
      <p v-if="props.leaf.part !== 0" class="leaf__cont">
        {{ props.leaf.poem.title }}<span class="leaf__dot">·</span>{{ props.leaf.part + 1 }}/{{ props.leaf.parts }}
      </p>

      <div class="leaf__verse" :class="{ 'leaf__verse--paired': props.leaf.orig }">
        <p
          v-for="(line, i) in props.leaf.lines"
          :key="i"
          class="leaf__line"
        >{{ line }}</p>
      </div>

      <!-- The poem in its own language, under the translation. It is set at the
           same measure as the Chinese but a step quieter, so the two read as one
           poem rather than two: 郑振铎's 飞鸟集 is the reading text, Tagore's
           English is what it was made from. -->
      <div v-if="props.leaf.orig" class="leaf__orig" :lang="props.leaf.poem.olang">
        <p
          v-for="(line, i) in props.leaf.orig"
          :key="i"
          class="leaf__oline"
        >{{ line }}</p>
      </div>
    </div>
  </article>
</template>

<style scoped>
/* The rule between the two texts belongs to the Chinese block, not to the
   English: hung on the translation it spans the *English* line, which is
   usually wider, so it shoots out past the poem on both sides and reads as a
   rule drawn across the canvas. On the verse it is exactly as wide as the poem
   it is stitching, and both texts stay centred on the same axis. */
.leaf__verse--paired {
  padding-bottom: 1.5em;
  border-bottom: 1px solid var(--line);
}

.leaf__orig {
  width: fit-content;
  max-width: 100%;
  margin: 1.9em auto 0;
  font-size: clamp(0.94rem, 1.7vw, 1.1rem);
  line-height: 1.95;
  letter-spacing: 0.02em;
  color: var(--faint);
}

.leaf__cont {
  font-size: var(--micro);
  letter-spacing: 0.32em;
  color: var(--faint);
  margin-bottom: 2.4em;
  text-indent: 0.32em;
}

.leaf__dot {
  margin: 0 0.6em;
  color: var(--faint);
}
</style>
