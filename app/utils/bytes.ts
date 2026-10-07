/**
 * Every file the corpus serves is stored gzipped, and the bytes are sniffed
 * rather than assumed.
 *
 * The compression is worth doing here because the sizes are not marginal: the
 * ten label columns come to 1.6 MB of little-endian codes and gzip takes them
 * to 201 KB, and the text chunks hold ~8 KB of JSON apiece and come down to
 * ~3.4 KB. How well a column compresses follows how much it actually says —
 * 语言 is 125 KB that is almost all one value and gzips 605:1, while 情绪 is a
 * real bitfield and only reaches 2:1.
 *
 * It has to be done by the site, not the host. GitHub Pages sets its own
 * caching policy and offers no way to set `Content-Encoding`, so a static
 * deploy cannot ask for the compression it needs. That leaves one hazard — a
 * host that *does* decide to compress a `.gz` it recognises would hand back the
 * payload already unwrapped, and a second gunzip would fail — so the first two
 * bytes are checked instead: gzip's magic is either there or it is not, and
 * both answers are read correctly.
 */

import { CORPUS_BUILD } from '~/corpus-meta'

/** Gzip's two magic bytes, little-endian, so one integer comparison reads them. */
const GZIP_MAGIC = 0x8b1f

export function isGzip(bytes: Uint8Array): boolean {
  return bytes.length > 1 && (bytes[0]! | (bytes[1]! << 8)) === GZIP_MAGIC
}

/**
 * Inflate with the browser's own implementation. It is native, so it does not
 * occupy the main thread the way a JavaScript inflate would, and a reader on a
 * phone pays the same price as one on a desktop.
 */
async function gunzip(bytes: Uint8Array<ArrayBuffer>): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('这个浏览器没有 DecompressionStream，读不了语料')
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

/**
 * One artifact in flight at a time.
 *
 * The same column can be wanted by more than one caller in the same tick — the
 * facets panel asks for every axis at once and the stream asks for its own
 * filter — and a second request for a file already on the wire is a second
 * round trip for bytes that are already coming. The entry is dropped as soon as
 * the fetch settles, so this dedupes work and not memory.
 */
const inflight = new Map<string, Promise<Uint8Array>>()

/**
 * Where an artifact sits, relative to the deploy's base path.
 *
 * A GitHub Pages project site is served from a subpath — `/poetry/` — and
 * `app.baseURL` follows it (the deploy workflow sets `NUXT_APP_BASE_URL`, and
 * nuxt.config joins the favicon by hand for the same reason). The paths the
 * corpus asks for are written site-relative, so every one of them has to be
 * joined onto that base: a leading slash resolves to the *origin* root, which
 * is the same thing locally and a 404 on the real deploy. That was a real
 * failure — the deployed page asked for `/corpus/t/19628.json.gz`, got an HTML
 * 404, and printed `Error: 404 File not found` where the poem should be —
 * while dev and the root-served build were both fine.
 *
 * `app/plugins/base.ts` sets that base from `app.baseURL` at startup (Vite's
 * own `import.meta.env.BASE_URL` is the base of the *bundle*, which the dev
 * server sets to `/_nuxt/`, and that cost another round of this exact failure).
 *
 * It is joined here, in the one function that fetches, rather than at the five
 * call sites: a call site that forgets is a whole feature quietly missing, and
 * there is no reason for anything downstream to know about deployment paths.
 */
let base: string | null = null

/** Set once, by the plugin that reads `app.baseURL`. Trailing slash trimmed. */
export function setBase(value: string): void {
  base = value.replace(/\/$/, '')
}

/** `'/corpus/x'` -> `'/corpus/x'` at the root, `'/poetry/corpus/x'` on a project site. */
export function sitePath(path: string): string {
  if (base === null) {
    // Loud on purpose: the alternative is asking the origin root for a file
    // that is not there, which looks like a missing file rather than a missing
    // base — and only on a subpath deploy, where nobody is looking.
    throw new Error(`sitePath('${path}') before the base was set — app/plugins/base.ts has not run`)
  }
  return base + path
}

/**
 * Fetch one artifact and hand back the bytes it holds, gzipped or not.
 *  `path` is site-relative and starts with a slash: `'/corpus/t/00000.json.gz'`.
 *
 * Everything under `/corpus/` is fetched with the corpus stamp in the query.
 * The host caches these files `immutable` — they are content-addressed by the
 * stamp, not by path — so a rebuilt corpus must arrive under new URLs or a
 * returning reader goes on serving a year-old corpus to a fresh bundle, and
 * the first thing to notice is the stamp check failing in useSearch. With the
 * stamp in the URL, a new corpus is simply new URLs.
 */
export function fetchBytes(path: string): Promise<Uint8Array> {
  const stamped = path.startsWith('/corpus/') ? `${path}?v=${CORPUS_BUILD}` : path
  const url = sitePath(stamped)
  let hit = inflight.get(url)
  if (!hit) {
    hit = fetch(url)
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`)
        const raw = new Uint8Array(await res.arrayBuffer())
        return isGzip(raw) ? await gunzip(raw) : raw
      })
      .finally(() => inflight.delete(url))
    inflight.set(url, hit)
  }
  return hit
}

/** Fetch one artifact and parse it as JSON. Small files go through this too.
 *  `path` is site-relative, like `fetchBytes`. */
export async function fetchJson<T>(path: string): Promise<T> {
  return JSON.parse(new TextDecoder().decode(await fetchBytes(path))) as T
}
