import { loadPoems } from '../utils/poems'

/**
 * Returns every poem, newest first. Runs on the server during prerender and is
 * inlined into the static payload, so the client never reads the filesystem.
 */
export default defineEventHandler(() => loadPoems())
