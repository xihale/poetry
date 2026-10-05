import type { Ref } from 'vue'
import type { Poem } from '~/types/poem'

/**
 * The poem index. Fetched once under a shared key: the first caller performs the
 * request, every other page reuses the same payload entry.
 */
export function usePoems() {
  return useAsyncData<Poem[]>('poems', () => $fetch('/api/poems'), {
    default: () => [],
  })
}

/** Everything a reading page needs, derived from the already-resolved index. */
export function usePoemView(poems: Ref<Poem[]>, id: string) {
  return computed(() => {
    const n = Number.parseInt(id, 10)
    const list = poems.value ?? []
    const i = list.findIndex((p) => p.id === n)
    // The list runs newest first, so the previous poem is the newer neighbour.
    return {
      list,
      poem: i === -1 ? null : list[i]!,
      prev: i > 0 ? list[i - 1]! : null,
      next: i !== -1 && i < list.length - 1 ? list[i + 1]! : null,
    }
  })
}
