<script setup lang="ts">
import { AXES, EMPTY_FILTER } from '~/types/poem'
import type { Anchor, Axis, Filter, Leaf } from '~/types/poem'
import type { Corpus } from '~/composables/useCorpus'
import { leavesOf } from '~/composables/usePoems'
import { fromHash, prune, sameFilter, toHash } from '~/composables/filterPath'

/**
 * The address the page was opened on, read out of the document's own navigation
 * entry rather than out of `location`.
 *
 * `location.hash` is not trustworthy at this point in a page's life: measured
 * on a fresh load of `/#author=李白`, the head script, a zero-delay timeout and
 * the navigation entry all have the fragment while the first read inside the
 * app does not — the fragment is applied to the URL a moment after the document
 * is committed. Reading it then means opening the whole canon for a shared link,
 * which is the exact failure the address is kept for. The navigation entry is
 * the URL the document was navigated to and is correct from the first script,
 * so it answers this one question; everything after this point goes through
 * `hashchange`, which fires when the address really does change.
 */
function openedOn(): string {
  if (location.hash) return location.hash
  const nav = performance.getEntriesByType('navigation')[0] as
    | PerformanceNavigationTiming
    | undefined
  if (!nav?.name) return ''
  try {
    return new URL(nav.name).hash
  } catch {
    return ''
  }
}

useHead({
  title: '白卷 · 中国诗选',
  meta: [{ name: 'theme-color', content: '#faf9f6' }],
})

// The corpus is 125,314 poems and none of it is held in the browser as objects.
// The labels ride in the text chunks, twenty poems to a file, so a drawn poem
// arrives with everything the leaf prints about it in one small request and
// nothing is fetched ahead of the poem the reader is reading. Filtering is the
// exception: it has to look at every poem's label, so the axis columns it looks
// at are fetched when the filter is applied. So the stream is built
// asynchronously: `fill` draws ids, awaits their text, and appends the leaves.
//
// It is loaded on the client, never on the server: the poem is chosen per visit
// so there is nothing to render ahead of time, and shipping any of the corpus
// through SSR would put the reader's own draw in the document.
const corpus = shallowRef<Corpus | null>(null)

const filter = ref<Filter>({ ...EMPTY_FILTER })
const leaves = ref<Leaf[]>([])
const panel = ref(false)
/** The axis the panel should open with, when a label sent the reader there. */
const panelAxis = ref<Axis | null>(null)
/** 寻句 — the search surface, over the whole corpus. */
const finding = ref(false)
/** The character that opened the search, so the first keystroke is not lost. */
const findingSeed = ref('')

/** The open chooser: which axis, the label that opened it, and where it sits. */
const menu = ref<{ axis: Axis; el: HTMLElement; anchor: Anchor } | null>(null)
const stream = ref<HTMLElement>()

/** The poems the current filter leaves, as corpus indices. */
const pool = ref<Uint32Array>(new Uint32Array())

/**
 * Read the pool the filter leaves out of the corpus. It is not computed here
 * and it cannot fail: `adopt` fetches whatever a filter is answered from before
 * the filter is adopted, so by the time this runs the columns are in hand.
 */
function repool() {
  if (corpus.value) pool.value = corpus.value.pool(filter.value)
}

/**
 * The draw is the pool shuffled once per cycle and walked down by a cursor.
 *
 * It used to be a copy of the whole pool with everything already taken filtered
 * out — for the unfiltered canon that is a 125,314-element array, a second one
 * from the filter, and a third from the shuffle, to pick one poem at random.
 * Shuffling the pool in place costs nothing and the pool's order is not a fact
 * about the corpus, so nothing is lost.
 *
 * `shown` counts the poems drawn since the last reset, which is the number the
 * stream is filled to. It is deliberately NOT reset when the pile runs out: a
 * collection of two poems still has to fill the screen, so the pile cycles
 * while `shown` climbs toward `want`. Resetting it at the cycle boundary is
 * what made a small collection hang — `shown` could never reach a `want` bigger
 * than the pool, so the pump never stopped fetching poems.
 */
let bag: Uint32Array | null = null
let cursor = 0
let shown = 0
/** The poem on screen, so the next cycle does not open with the same one. */
let skip = -1

function draw(): number | null {
  if (!bag || cursor === 0) {
    const next = pool.value
    if (!next.length) return null
    for (let i = next.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      const swap = next[i]!
      next[i] = next[j]!
      next[j] = swap
    }
    bag = next
    cursor = next.length
    if (bag[cursor - 1] === skip) {
      bag[cursor - 1] = bag[0]!
      bag[0] = skip
    }
  }
  cursor--
  shown++
  return bag[cursor]!
}

/**
 * How many poems the stream should hold, and a generation counter that a reset
 * bumps. Drawing is asynchronous — a poem's text is a fetch — so a reset can
 * land in the middle of one. Without the generation the in-flight draw would
 * append leaves from the pool the reader has already left; without the `want`
 * re-check it would also finish and never restart, leaving a blank page.
 */
let want = 2
let gen = 0
let pumping = false
let pending = false

/**
 * Keep at least `min` poems in the stream, so there is always a next one.
 *
 * Drawing is serialised: two pumps at once would both pop from `bag` and could
 * show the same poem twice, and the text fetches would race to append leaves
 * out of order. A pump that is interrupted by a reset sets `pending`, and the
 * pump loop picks the new target up rather than returning with nothing drawn.
 */
async function fill(min: number) {
  want = min
  if (pumping) {
    // A pump is mid-await on a text fetch. It cannot be restarted from here —
    // the generation it is holding is stale and it will break out — so it is
    // told to run again with the new target once it lands.
    pending = true
    return
  }
  pumping = true
  try {
    do {
      pending = false
      const mine = gen
      while (shown < want && gen === mine) {
        const id = draw()
        if (id === null) break
        const poem = await corpus.value!.poem(id)
        if (gen !== mine) {
          pending = true
          break
        }
        leaves.value.push(...leavesOf(poem))
      }
    } while (pending)
  } catch (err) {
    // a text chunk that will not load is a failure the reader has to see: the
    // stream would otherwise just stop, with no way to tell a broken fetch from
    // a filter that matches nothing
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    console.error('corpus draw failed', err)
  } finally {
    pumping = false
  }
}

function reset() {
  bag = null
  cursor = 0
  shown = 0
  skip = -1
  leaves.value = []
  gen++
  repool()
  // a new draw starts at the top, with the paging state cleared so the first
  // gesture after it is not swallowed by the turn that just happened
  turning = false
  goal = 0
  spent = false
  acc = 0
  clearTimeout(turnTimer)
  stream.value?.scrollTo({ top: 0 })
  void fill(2)
}

/**
 * Adopt a filter — once the corpus holds what answering it takes.
 *
 * A filter is a request before it is a state. Its column is fetched, not
 * resident, and `pool` and the counts read that column directly, so setting a
 * filter ahead of its column is setting one that nothing can answer. The fetch
 * is therefore part of applying it, and `counting` names the axes whose choices
 * are about to be *shown*, because those counts are read out of their columns
 * too. Only the first use of an axis costs anything; what has been read stays
 * for the life of the page.
 *
 * The generation guard is for the reader who uses the back button twice: two
 * filters can be loading at once, and only the one the address ends on may win.
 */
let adopting = 0

async function adopt(next: Filter, counting: Axis[] = [], write = true) {
  if (sameFilter(next, filter.value)) return
  const mine = ++adopting
  try {
    await corpus.value!.ready(next, counting)
  } catch (err) {
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    console.error('corpus filter failed', err)
    return
  }
  if (mine !== adopting) return
  // A filter is a request, and an address outlives the corpus it was written
  // against: it can name a 作者 this build does not carry. The axes are dropped
  // in fromHash and the values are dropped here, where the dictionaries that
  // answer the question have just been loaded — a link naming a poet who is
  // gone opens the poems that are still there. Without this the value reaches
  // the column read and throws, after the filter is already set.
  filter.value = prune(next, (axis, value) => corpus.value!.has(axis, value))
  if (write) writePath()
  reset()
}

/**
 * The axes the panel's counts will have to be read out of, given a filter.
 *
 * Open with nothing narrowed, the panel prints the corpus's own counts and the
 * answer is an empty list — a request for those counts and nothing else. Closed,
 * there is nothing to count and the answer is nothing at all.
 */
function countable(next: Filter): Axis[] | undefined {
  if (!panel.value) return undefined
  return AXES.some((a) => next[a.key]) ? AXES.map((a) => a.key) : []
}

function toggle(axis: Axis, value: string) {
  const next = { ...filter.value, [axis]: filter.value[axis] === value ? null : value }
  void adopt(next, countable(next))
}

function clearAll() {
  const next = { ...EMPTY_FILTER }
  void adopt(next, countable(next))
}

/**
 * ── the filter as a path ──────────────────────────────────────────────────
 *
 * The filter lives in the URL hash (see composables/filterPath.ts), so a
 * narrowed collection can be shared, reloaded and stepped out of with the back
 * button.
 *
 * The history is written with `pushState`, not by assigning `location.hash`.
 * That is deliberate twice over: it gives the first filter a history entry the
 * reader can back out of instead of replacing the page they arrived on, and it
 * fires no event — so the app never has to tell its own writes apart from the
 * reader's navigation. `popstate` and `hashchange` therefore only ever mean
 * *someone else* moved: the back button, a pasted link, a hand-edited hash.
 */
function writePath(replace = false) {
  if (typeof window === 'undefined') return
  const next = toHash(filter.value)
  const here = `${location.pathname}${location.search}${location.hash}`
  const url = `${location.pathname}${location.search}${next ? `#${next}` : ''}`
  if (url === here) return
  if (replace) history.replaceState(null, '', url)
  else history.pushState(null, '', url)
}

/** Adopt wherever the address now points, if it is not where we already are. */
function onPathChange() {
  if (typeof window === 'undefined') return
  const next = fromHash(location.hash)
  // the address already says this, so adopting it must not write it again
  void adopt(next, countable(next), false)
}

/**
 * Read a poem the reader picked out of the search results.
 *
 * It is put at the head of the stream and the stream goes back to the top, so
 * the poem they chose is the poem they are looking at — not something to hunt
 * for. The drawn pile is cleared but the filter is not: searching is a way of
 * reading, not a filter, and the reader's own 分类 choices must survive it.
 */
async function showPoem(id: number) {
  finding.value = false
  gen++
  bag = null
  cursor = 0
  // the chosen poem is on screen, so it counts as drawn: this is what stops the
  // stream opening with the poem the reader is already looking at
  shown = 1
  skip = id
  leaves.value = leavesOf(await corpus.value!.poem(id))
  turning = false
  goal = 0
  spent = false
  acc = 0
  clearTimeout(turnTimer)
  stream.value?.scrollTo({ top: 0 })
  // top the stream up behind it
  void fill(2)
}

/**
 * Open the choices for the label that was clicked, or close on a second click.
 *
 * The chooser prints a count beside every one of the axis's values, and those
 * counts are read out of the axis's column — two of them, this axis and
 * whichever one the reader has already used. So the menu opens with the numbers
 * rather than opening and then filling in. Clicking labels quickly is handled
 * by the generation counter: only the last one asked for may open.
 */
let menuing = 0
async function openMenu(payload: { axis: Axis; el: HTMLElement; anchor: Anchor }) {
  if (menu.value?.el === payload.el) {
    closeMenu()
    return
  }
  const mine = ++menuing
  try {
    await corpus.value!.ready(filter.value, [payload.axis])
  } catch (err) {
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    return
  }
  if (mine !== menuing) return
  menu.value = payload
}

function closeMenu() {
  const el = menu.value?.el
  menu.value = null
  menuing++
  // never yank the poem back into view just because the pointer left the menu
  el?.focus({ preventScroll: true })
}

/**
 * A choice from the chooser; 全部 clears the axis.
 *
 * Unlike 分类's chips, this one does not write the address — that is how it
 * already behaved, not a decision this change made, and it means a filter
 * chosen from a leaf leaves the hash where it was. Left as it was: it is not
 * obviously wrong (the next 分类 choice or reload decides) but it is not
 * obviously right either, and it should be settled on purpose rather than
 * changed in passing.
 */
function choose(value: string | null) {
  const axis = menu.value?.axis
  menu.value = null
  menuing++
  if (!axis) return
  const next = { ...filter.value, [axis]: value }
  void adopt(next, countable(next))
}

/** The axis was longer than the chooser lists — hand it to the panel, opened. */
function moreFacets() {
  panelAxis.value = menu.value?.axis ?? null
  menu.value = null
  menuing++
  void showPanel()
}

/** 分类 was asked for, and is opened once its counts can be printed. */
async function openPanel() {
  panelAxis.value = null
  await showPanel()
}

/**
 * Open 分类 with the numbers it is about to show.
 *
 * With nothing filtered the panel costs nothing at all: the counts it prints
 * are the corpus's own, counted at build time, and they arrive in one small
 * file. The moment one axis is narrowed, every other axis's counts have to be
 * read out of its column — that is the one place this site spends real bytes on
 * a reader's behalf, and it is the point of the design: a reader who filters
 * pays for the columns they filter by, and a reader who only reads pays for
 * none of it. The old index made everyone pay 11 MB on arrival, for this.
 */
const counting = ref(false)

async function showPanel() {
  const axes = AXES.map((a) => a.key)
  // nothing narrowed: the panel prints the corpus's own counts, which are one
  // small file and no column at all
  const narrowed = axes.some((key) => filter.value[key])
  counting.value = narrowed
  try {
    await corpus.value!.ready(filter.value, narrowed ? axes : [])
  } catch (err) {
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    console.error('corpus facets failed', err)
    counting.value = false
    return
  }
  counting.value = false
  panel.value = true
}

/** The two controls are one row at the foot of the page, so neither moves. */

/** ── turning the page ─────────────────────────────────────────────────────
 * The stream is read one screen at a time: a wheel notch, a trackpad push or
 * a swipe turns exactly one page, and neither the tail of a trackpad's
 * inertia nor a hard spin of the wheel queues up more. A gesture is over once
 * the input has been quiet for GAP; only then does the next one count. Pages
 * are one viewport tall, so a leaf taller than the screen takes two gestures
 * to read through, the way a book does.
 */
const STEP = 24 // accumulated intent, in px, that counts as a gesture
const GAP = 140 // ms of silence that separates two gestures
const LOCK = 560 // ms a page turn takes; input during it is swallowed
const SWIPE = 28 // px of touch travel that counts as a swipe

let goal = 0
let turning = false
let turnTimer: ReturnType<typeof setTimeout> | undefined
let acc = 0
let lastEvent = 0
let spent = false // this gesture has already turned a page

const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** One page in `dir`. Measured from the target, not from the frame the last
 *  turn happens to be showing, so a turn interrupted mid-animation still lands
 *  a whole page on. */
function turn(dir: number) {
  const el = stream.value
  if (!el) return
  const max = Math.max(0, el.scrollHeight - el.clientHeight)
  const from = turning ? goal : el.scrollTop
  goal = Math.min(max, Math.max(0, from + dir * el.clientHeight))
  turning = true
  el.scrollTo({ top: goal, behavior: calm() ? 'auto' : 'smooth' })
  clearTimeout(turnTimer)
  turnTimer = setTimeout(() => {
    turning = false
    goal = el.scrollTop
  }, LOCK)
}

/** Wheel travel in px: lines and pages arrive as counts, not pixels. */
function travel(e: WheelEvent) {
  if (e.deltaMode === 1) return e.deltaY * 16
  if (e.deltaMode === 2) return e.deltaY * window.innerHeight
  return e.deltaY
}

function onWheel(e: WheelEvent) {
  if (e.ctrlKey) return // pinch-zoom, not a scroll
  const dy = travel(e)
  if (!dy || Math.abs(dy) < Math.abs(e.deltaX)) return
  e.preventDefault()
  const now = performance.now()
  if (now - lastEvent > GAP) {
    spent = false
    acc = 0
  }
  lastEvent = now
  if (spent) return
  acc += dy
  if (Math.abs(acc) < STEP) return
  spent = true
  const dir = Math.sign(acc)
  acc = 0
  turn(dir)
}

let touchY = 0
let touchSpent = false

function onTouchStart(e: TouchEvent) {
  touchY = e.touches[0]!.clientY
  touchSpent = false
}

function onTouchMove(e: TouchEvent) {
  // the stream is paged, never dragged: a swipe is a page turn, not a scroll
  e.preventDefault()
  if (touchSpent) return
  const dy = touchY - e.touches[0]!.clientY // finger up = forward
  if (Math.abs(dy) < SWIPE) return
  touchSpent = true
  turn(dy > 0 ? 1 : -1)
}

function onScroll() {
  const el = stream.value
  if (!el) return
  if (!turning) goal = el.scrollTop
  if (menu.value) closeMenu()
  if (el.scrollTop + el.clientHeight > el.scrollHeight - el.clientHeight) {
    void fill(shown + 1)
  }
}

function onPointerDown(e: PointerEvent) {
  if (!menu.value) return
  const el = menu.value.el
  if (el.contains(e.target as Node)) return
  const sheet = document.querySelector('.menu')
  if (sheet?.contains(e.target as Node)) return
  closeMenu()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (menu.value) closeMenu()
    else if (finding.value) finding.value = false
    else panel.value = false
    return
  }
  // Every open surface owns the keyboard. This is not just about Esc: the paging
  // keys below call preventDefault, so a space typed into the search field would
  // be swallowed and would turn a page behind the panel.
  if (panel.value || menu.value || finding.value) return
  // typing anywhere on the reading surface starts a search: there is no other
  // way to want a text field, and the surface has nothing else to type into.
  // e.key is the character the layout produced, so a Chinese IME that delivers
  // 床 as one keypress opens search exactly as an ASCII letter does.
  if (!e.metaKey && !e.ctrlKey && !e.altKey && [...e.key].length === 1 && /\S/u.test(e.key)) {
    // The character that opened the panel is the first character of the query.
    // It is carried explicitly, and the key's own default action is suppressed,
    // because otherwise the browser may *also* insert it — once the panel has
    // rendered, the field is focused, and one keystroke lands twice.
    e.preventDefault()
    findingSeed.value = e.key
    finding.value = true
    return
  }
  // the stream is its own scroll container, so the browser's default paging
  // keys never reach it — the page turn has to be driven here, through the
  // same debounce, so a held key does not spin through the whole collection
  const now = performance.now()
  if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ' ||
      e.key === 'ArrowUp' || e.key === 'PageUp') {
    e.preventDefault()
    if (now - lastEvent > GAP) spent = false
    lastEvent = now
    if (spent) return
    spent = true
    turn(e.key === 'ArrowUp' || e.key === 'PageUp' ? -1 : 1)
  } else if (e.key === 'ArrowRight') {
    reset()
  }
}

function onTouchEnd() {
  touchY = 0
}

/**
 * A Chinese reader reaches the site through an IME, and an IME does not deliver
 * the character as a keypress: the keystrokes arrive as `Process` while the
 * candidate list is up, and the character that was actually chosen arrives as a
 * `compositionend` on whatever element has focus. On the reading surface that
 * element is the body, so the character would simply be lost.
 *
 * This is the path that has to work on a Chinese corpus, so it is handled
 * directly: a composition that ends anywhere but inside the search field opens
 * search with the composed text.
 */
function onCompositionEnd(e: CompositionEvent) {
  if (finding.value || panel.value || menu.value) return
  const text = (e.data || '').trim()
  if (!text) return
  findingSeed.value = text
  finding.value = true
}

/** Shown when the corpus cannot be fetched at all — a blank screen tells the
 *  reader nothing, and this site has no other chrome to carry a message. */
const failure = ref('')

/**
 * The two controls surface when the pointer moves and fade when it rests, and
 * the pointer itself goes with them.
 *
 * A reader who is not moving the mouse is reading, and reading is the only thing
 * this page is for — so the controls are absent by default. The timer is why
 * this is not a CSS `:hover`: a CSS hover shows the controls when the pointer is
 * *over* them, which is exactly when the reader is least likely to be reading,
 * and hides them the moment it leaves. What is wanted is the opposite rule —
 * shown after any pointer movement, hidden after it has been still.
 *
 * Scrolling counts as movement: the wheel is a pointer event, and a reader who
 * is turning pages should be able to reach for a control without first jiggling
 * the mouse. A touch device never sees any of this — the stylesheet only applies
 * the hidden state under `hover: hover`, where there is an idle pointer to wait
 * for, and `cursor: none` means nothing where there is no cursor.
 */
const AWAKE = 2600
const awake = ref(false)
let doze: ReturnType<typeof setTimeout> | undefined

/** Put the page to sleep: controls gone, pointer gone. */
function rest() {
  awake.value = false
  document.documentElement.classList.add('cursor-idle')
}

/** Any activity brings both back, and starts the countdown again. */
function wake() {
  awake.value = true
  document.documentElement.classList.remove('cursor-idle')
  clearTimeout(doze)
  doze = setTimeout(rest, AWAKE)
}

onMounted(async () => {
  // the address is read before the first draw, so a shared link opens on the
  // collection it names rather than on the whole canon and then correcting
  filter.value = fromHash(openedOn())
  try {
    const loaded = await useCorpus()
    corpus.value = loaded
    // a shared link arrives already narrowed, so the columns its filter reads
    // are fetched before the first draw rather than after it
    await loaded.ready(filter.value)
    // and the link can outlive what it names, so its values are tested against
    // the dictionaries that just arrived (see filterPath.prune)
    filter.value = prune(filter.value, (axis, value) => loaded.has(axis, value))
  } catch (err) {
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    console.error('corpus load failed', err)
    return
  }
  window.addEventListener('keydown', onKey)
  window.addEventListener('compositionend', onCompositionEnd)
  window.addEventListener('pointerdown', onPointerDown)
  window.addEventListener('popstate', onPathChange)
  window.addEventListener('hashchange', onPathChange)
  window.addEventListener('pointermove', wake, { passive: true })
  window.addEventListener('pointerdown', wake, { passive: true })
  window.addEventListener('wheel', wake, { passive: true })
  // The page opens at rest — the controls are away until the reader moves — but
  // the pointer is the reader's own tool and is not taken from them on arrival.
  // It goes when it has been still for the same count, like everything else.
  doze = setTimeout(rest, AWAKE)
  // a non-passive listener: the wheel is read, not followed
  stream.value?.addEventListener('wheel', onWheel, { passive: false })
  stream.value?.addEventListener('touchstart', onTouchStart, { passive: true })
  stream.value?.addEventListener('touchmove', onTouchMove, { passive: false })
  stream.value?.addEventListener('touchend', onTouchEnd, { passive: true })
  // The first draw is the last thing that can fail with the page already
  // standing, and the controls are what a reader would reach for — so they are
  // listening by now, and a failure here is a line beside them rather than a
  // page that answers nothing.
  try {
    repool()
    void fill(2)
  } catch (err) {
    failure.value = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
    console.error('corpus draw failed', err)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('compositionend', onCompositionEnd)
  window.removeEventListener('pointerdown', onPointerDown)
  window.removeEventListener('popstate', onPathChange)
  window.removeEventListener('hashchange', onPathChange)
  window.removeEventListener('pointermove', wake)
  window.removeEventListener('pointerdown', wake)
  window.removeEventListener('wheel', wake)
  document.documentElement.classList.remove('cursor-idle')
  clearTimeout(doze)
  stream.value?.removeEventListener('wheel', onWheel)
  stream.value?.removeEventListener('touchstart', onTouchStart)
  stream.value?.removeEventListener('touchmove', onTouchMove)
  stream.value?.removeEventListener('touchend', onTouchEnd)
  clearTimeout(turnTimer)
})
</script>

<template>
  <div>
    <div ref="stream" class="stream" role="region" aria-label="诗" @scroll.passive="onScroll">
      <PoemLeaf
        v-for="leaf in leaves"
        :key="leaf.key"
        :leaf="leaf"
        :filter="filter"
        @pick="openMenu"
      />
      <p v-if="failure" class="empty">{{ failure }}</p>
      <p v-else-if="corpus && !leaves.length" class="empty">此卷无诗</p>
    </div>

    <button
      class="edge edge--find"
      :class="{ 'edge--awake': awake }"
      aria-label="寻句"
      @click="findingSeed = ''; finding = true"
    >寻</button>
    <button
      class="edge edge--facets"
      :class="{ 'edge--awake': awake || counting }"
      :aria-busy="counting"
      aria-label="分类"
      @click="openPanel"
    >类</button>

    <Transition name="menu">
      <FacetMenu
        v-if="menu && corpus"
        :key="menu.axis"
        :axis="menu.axis"
        :anchor="menu.anchor"
        :corpus="corpus"
        :filter="filter"
        @pick="choose"
        @more="moreFacets"
        @close="closeMenu"
      />
    </Transition>

    <Transition name="panel">
      <SearchPanel
        v-if="finding && corpus"
        :corpus="corpus"
        :seed="findingSeed"
        @go="showPoem"
        @close="finding = false"
      />
    </Transition>

    <Transition name="panel">
      <Facets
        v-if="panel && corpus"
        :corpus="corpus"
        :filter="filter"
        :opened="panelAxis"
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
  color: var(--faint);
  letter-spacing: 0.5em;
  text-indent: 0.5em;
}
</style>
