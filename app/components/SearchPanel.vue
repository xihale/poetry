<script setup lang="ts">
import type { Corpus } from '~/composables/useCorpus'
import { useSearch } from '~/composables/useSearch'
import type { Hit } from '~/composables/useSearch'

const props = defineProps<{
  corpus: Corpus
  /** The character typed on the reading surface that opened this panel. */
  seed?: string
}>()

const emit = defineEmits<{
  (e: 'go', id: number): void
  (e: 'close'): void
}>()

const search = useSearch(props.corpus)

/**
 * How many poems are on the site, for the hint. Derived from the corpus rather
 * than written down: the number has already changed once (458,317 → 125,314),
 * and a hint that lies about the size of the library is the one lie a reader
 * can check against nothing.
 */
const wan = computed(() => {
  const n = props.corpus.n
  return n >= 10000 ? `${Math.round(n / 1000) / 10} 万` : String(n)
})

const query = ref('')
const hits = ref<Hit[]>([])
const complete = ref(true)
const busy = ref(false)
/** The index could not be loaded — see the note on the query watcher. */
const failed = ref(false)
const cursor = ref(0)

/**
 * A query in flight must not overwrite a newer one. Each run takes a token and
 * only the newest may write its results — otherwise typing 「明月几」 and then
 * 「静夜思」 can leave the first one's results on screen.
 */
let token = 0
let timer: ReturnType<typeof setTimeout> | undefined

watch(query, (value) => {
  clearTimeout(timer)
  const trimmed = value.trim()
  if (trimmed.length < 2) {
    hits.value = []
    complete.value = true
    busy.value = false
    failed.value = false
    return
  }
  busy.value = true
  // a reader types faster than shards load; waiting for a pause is what keeps
  // one keystroke from firing a dozen shard fetches
  timer = setTimeout(async () => {
    const mine = ++token
    try {
      const found = await search.run(trimmed)
      if (mine !== token) return
      failed.value = false
      hits.value = found.hits
      complete.value = found.complete
      cursor.value = 0
    } catch (err) {
      // The index is fetched per query and can be absent, half-built, or built
      // from another corpus — and 「寻…」 for good is not a state a reader can do
      // anything about. It says so, and the detail goes to the console.
      if (mine === token) {
        failed.value = true
        hits.value = []
      }
      console.error('search failed', err)
    } finally {
      if (mine === token) busy.value = false
    }
  }, 160)
})

/** The matched span, so the line the reader half-remembers shows the words. */
function parts(hit: Hit) {
  const [a, b] = hit.mark
  return { before: hit.line.slice(0, a), match: hit.line.slice(a, b), after: hit.line.slice(b) }
}

function go(hit: Hit | undefined) {
  if (hit) emit('go', hit.id)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
    return
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    if (!hits.value.length) return
    const dir = e.key === 'ArrowDown' ? 1 : -1
    cursor.value = (cursor.value + dir + hits.value.length) % hits.value.length
    document.querySelector('.hit--cursor')?.scrollIntoView({ block: 'nearest' })
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    go(hits.value[cursor.value])
  }
}

const input = ref<HTMLInputElement>()
onMounted(() => {
  if (props.seed) query.value = props.seed
  input.value?.focus()
})
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <section class="panel" aria-label="寻句" @keydown="onKey">
    <div class="panel__inner">
      <input
        ref="input"
        v-model="query"
        class="find"
        type="search"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        aria-label="在全部诗句中查找"
        placeholder="一句诗"
      />

      <p class="find__count">
        <template v-if="busy">寻…</template>
        <template v-else-if="failed">寻句暂时不可用</template>
        <template v-else-if="!query.trim()">输入两个字以上，在 {{ wan }}首里找</template>
        <template v-else-if="!hits.length">没有这一句</template>
        <template v-else-if="complete">{{ hits.length }} 首</template>
        <template v-else>前 {{ hits.length }} 首</template>
      </p>

      <ol v-if="hits.length" class="hits">
        <li v-for="(hit, i) in hits" :key="hit.id">
          <button
            class="hit"
            :class="{ 'hit--cursor': i === cursor }"
            @click="go(hit)"
            @mousemove="cursor = i"
          >
            <span class="hit__line">
              {{ parts(hit).before }}<mark>{{ parts(hit).match }}</mark>{{ parts(hit).after }}
            </span>
            <span class="hit__where">
              <!-- A title match has already printed the title as the line above,
                   so the apparatus starts at the author; repeating it here would
                   show the reader the same words twice and no verse at all. -->
              <template v-if="!hit.inTitle">{{ hit.title }}<span class="leaf__dot">·</span></template>{{ hit.author }}<span class="leaf__dot">·</span>{{ hit.coll }}
            </span>
          </button>
        </li>
      </ol>

      <div class="panel__foot">
        <button @click="emit('close')">合卷</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 合卷 is the only way out of this panel, so it has to be reachable from
   wherever the reader is in the list. Results run to eighty rows and the list
   scrolls inside the panel, so the foot is pinned to the bottom edge of the
   viewport and the results scroll under it.
 
   It used to be `static`, to stop it floating mid-page in the short states
   (empty field, no results) — which it did, at the cost of putting the only
   exit seven thousand pixels down a list of eighty. The foot is now pinned and
   the short states are handled by the sheet itself: `.panel__inner` fills the
   scrollport, so with nothing in the list the foot sits at the bottom of a full
   sheet rather than just under the hint. */
.panel__foot {
  position: sticky;
  bottom: 0;
  margin-top: auto;
  padding: 1.2rem 0 1.4rem;
  background: var(--paper);
}

/* The one field on the site. It carries no box, no border and no background —
   a line of paper with a caret on it, at the weight of a title, so what the
   reader types is set in the same voice as what they are looking for. */
.find {
  width: 100%;
  padding: 0 0 0.5rem;
  font: inherit;
  font-size: clamp(1.4rem, 3.2vw, 1.9rem);
  font-weight: 300;
  letter-spacing: 0.12em;
  color: var(--ink);
  background: none;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  outline: none;
  appearance: none;
}

/* --faint, not --ghost: a placeholder is text the reader has to read to know
   what the field is for, and it is set at 1.4-1.9rem, below the large-text
   threshold where a lower ratio would be allowed. */
.find::placeholder {
  color: var(--faint);
  letter-spacing: 0.2em;
}

.find:focus {
  border-bottom-color: var(--faint);
}

/* the field is a search input, so the browser's own clear button has to go */
.find::-webkit-search-cancel-button {
  appearance: none;
}

.find__count {
  margin: 1.1rem 0 2.6rem;
  font-size: var(--micro);
  letter-spacing: 0.22em;
  color: var(--faint);
}

.hits {
  list-style: none;
  border-top: 1px solid var(--line);
}

.hit {
  display: block;
  width: 100%;
  padding: 1.15rem 0;
  text-align: left;
  border-bottom: 1px solid var(--line);
}

.hit__line {
  display: block;
  font-size: 1.06rem;
  line-height: 1.9;
  letter-spacing: 0.06em;
  color: var(--faint);
  transition: color 0.2s var(--ease);
}

.hit__where {
  display: block;
  margin-top: 0.5rem;
  font-size: var(--micro);
  letter-spacing: 0.22em;
  color: var(--faint);
}

/* the line the reader remembered is the one thing in ink; the words they
   searched for are the only thing that is not */
.hit--cursor .hit__line,
.hit:hover .hit__line {
  color: var(--ink);
}

.hit__line mark {
  color: var(--ink);
  background: none;
  font-weight: 400;
}

.hit--cursor .hit__line mark,
.hit:hover .hit__line mark {
  box-shadow: inset 0 -0.5em 0 var(--select);
}

@media (max-width: 600px) {
  .hit__line {
    font-size: 1rem;
  }
}
</style>
