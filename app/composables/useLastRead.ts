/**
 * Remembers which poem was read last, so the index can mark the reader's place.
 * Stored in localStorage; degrades to a no-op when storage is unavailable.
 */
const KEY = 'poetry:last-read'

export function useLastRead() {
  const lastRead = useState<number | null>('last-read', () => null)

  function mark(id: number) {
    lastRead.value = id
    try {
      localStorage.setItem(KEY, String(id))
    } catch {
      /* storage blocked: the in-memory value still works this session */
    }
  }

  function restore() {
    try {
      const raw = localStorage.getItem(KEY)
      if (raw !== null) lastRead.value = Number.parseInt(raw, 10)
    } catch {
      /* ignore */
    }
  }

  return { lastRead, mark, restore }
}
