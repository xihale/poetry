/**
 * Hand the deploy's base to the artifact fetcher before anything asks for one.
 *
 * The base is `app.baseURL` — `/` in dev, `/poetry/` on a GitHub Pages project
 * site — the same value the bundle's own asset URLs are built from, so the
 * corpus and the app can never disagree about where the page is.
 *
 * It comes through the runtime config, which only answers from inside a Nuxt
 * context; `utils/bytes.ts` is a plain module, so this is where the two meet.
 * Plugins run before the app mounts, and a corpus artifact is only ever asked
 * for from a reader's action or from a page's own `onMounted` — so the base is
 * in place before the first fetch. If that ever stops being true, `sitePath`
 * throws rather than fetching from the wrong place.
 *
 * Not `import.meta.env.BASE_URL`: that is the base of the *bundle*, and Nuxt's
 * dev server sets it to `/_nuxt/` (the prefix it serves app modules under), so
 * the corpus was asked for at `/_nuxt/corpus/t/05479.json.gz` and 404'd — in
 * dev only, which is the one place the mistake is cheap to find and expensive
 * to trust.
 */
import { setBase } from '~/utils/bytes'

export default defineNuxtPlugin((nuxtApp) => {
  setBase(nuxtApp.$config.app.baseURL)
})
