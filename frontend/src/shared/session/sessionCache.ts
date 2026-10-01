/**
 * Per-user caches register a reset callback here. Logging out or losing the session
 * clears them so the next person on the same device never sees old data.
 */
const resets = new Set<() => void>()

export function onSessionEnd(reset: () => void): () => void {
  resets.add(reset)
  return () => resets.delete(reset)
}

export function clearSessionCaches(): void {
  resets.forEach(reset => {
    try {
      reset()
    } catch {
      // A broken cache must not block logout.
    }
  })
}
