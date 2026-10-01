/**
 * Which portal the Firebase session belongs to. Owner app and Workshop Portal share
 * one Firebase project, so only the portal the user signed in through restores the
 * session automatically (US-013 FE §19). The value is not personal data.
 */
export type Portal = 'owner' | 'workshop'

const KEY = 'evcare.portal'

export function getPortal(): Portal | null {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'owner' || value === 'workshop' ? value : null
  } catch {
    return null
  }
}

export function setPortal(portal: Portal): void {
  try {
    localStorage.setItem(KEY, portal)
  } catch {
    // Storage unavailable: the session simply is not restored automatically.
  }
}

export function clearPortal(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}
