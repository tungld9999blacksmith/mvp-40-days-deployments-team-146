import { onSessionEnd } from '@/shared/session/sessionCache'

const PREFIX = 'evcare:current-vehicle:'

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

/** The vehicle this owner picked in the current session (reloads and new tabs keep it). */
export function readRememberedVehicle(userId: number): string | null {
  try {
    return storage()?.getItem(PREFIX + userId) ?? null
  } catch {
    return null
  }
}

export function rememberVehicle(userId: number, userVehicleId: string | null): void {
  try {
    const store = storage()
    if (!store) return
    if (userVehicleId) store.setItem(PREFIX + userId, userVehicleId)
    else store.removeItem(PREFIX + userId)
  } catch {
    // Private mode or blocked storage: the pick lasts until the next reload.
  }
}

/** Logging out forgets every pick, so the next sign-in asks again. */
export function forgetAllVehicles(): void {
  try {
    const store = storage()
    if (!store) return
    const keys: string[] = []
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index)
      if (key?.startsWith(PREFIX)) keys.push(key)
    }
    keys.forEach(key => store.removeItem(key))
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}

onSessionEnd(forgetAllVehicles)
