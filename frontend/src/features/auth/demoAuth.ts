/**
 * Stand-in for the Google account in demo mode (no Firebase). Like one Firebase project, a single
 * identity serves both portals; the portal backend (here the mock API) decides which account it
 * opens. The signed-in state survives reloads and is shared between tabs, as Firebase does.
 */

export interface AuthUser {
  uid: string
}

const KEY = 'evcare.demoAuth'
const DEMO_USER: AuthUser = { uid: 'demo-google-account' }
/** Picking an account in the Google popup takes a moment; keeps the loading state visible. */
const PICKER_DELAY_MS = 400

type Listener = (user: AuthUser | null) => void

const listeners = new Set<Listener>()
let memorySignedIn = false

function isSignedIn(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return memorySignedIn
  }
}

function setSignedIn(value: boolean) {
  memorySignedIn = value
  try {
    if (value) localStorage.setItem(KEY, '1')
    else localStorage.removeItem(KEY)
  } catch {
    // Storage blocked: the session lasts for this page only.
  }
}

function notify() {
  const user = demoCurrentUser()
  for (const listener of listeners) listener(user)
}

export function demoCurrentUser(): AuthUser | null {
  return isSignedIn() ? DEMO_USER : null
}

/** Same contract as Firebase `onAuthStateChanged`: the current state arrives asynchronously, then every change. */
export function demoSubscribe(listener: Listener): () => void {
  listeners.add(listener)
  const timer = window.setTimeout(() => listener(demoCurrentUser()), 0)
  return () => {
    window.clearTimeout(timer)
    listeners.delete(listener)
  }
}

export async function demoSignIn(): Promise<AuthUser> {
  await new Promise(resolve => window.setTimeout(resolve, PICKER_DELAY_MS))
  setSignedIn(true)
  notify()
  return DEMO_USER
}

export async function demoSignOut(): Promise<void> {
  setSignedIn(false)
  notify()
}

// Sign-in / sign-out in another tab.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key === KEY) notify()
  })
}
