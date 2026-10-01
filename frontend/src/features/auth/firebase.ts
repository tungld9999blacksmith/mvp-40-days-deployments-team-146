import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  connectAuthEmulator,
  getAuth,
  getRedirectResult,
  setPersistence,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth'
import { FirebaseError } from 'firebase/app'
import { firebaseAuthEmulatorUrl, firebaseConfig, isFirebaseConfigured } from '@/shared/config/env'

let auth: Auth | null = null

/** Firebase Auth instance, or `null` when VITE_FIREBASE_* is not configured. */
export function getFirebaseAuth(): Auth | null {
  if (!isFirebaseConfigured) return null
  if (!auth) {
    const app = initializeApp(firebaseConfig)
    auth = getAuth(app)
    auth.languageCode = 'vi'
    if (firebaseAuthEmulatorUrl) {
      connectAuthEmulator(auth, firebaseAuthEmulatorUrl, { disableWarnings: true })
    }
    // Keep the session across browser restarts (auto-login, US-007 / US-015).
    void setPersistence(auth, browserLocalPersistence)
  }
  return auth
}

/** Firebase error code such as `auth/popup-closed-by-user`, or null. */
export function firebaseErrorCode(error: unknown): string | null {
  return error instanceof FirebaseError ? error.code : null
}

const CANCELLED_CODES = new Set(['auth/popup-closed-by-user', 'auth/cancelled-popup-request', 'auth/user-cancelled'])

/** The user closed the Google popup: not an error to show (EDGE-101). */
export function isSignInCancelled(error: unknown): boolean {
  const code = firebaseErrorCode(error)
  return code !== null && CANCELLED_CODES.has(code)
}

/**
 * Opens the Google account picker. Falls back to a full-page redirect when the
 * browser blocks popups; in that case the promise resolves to `null` and the
 * result is picked up by `onAuthStateChanged` after the redirect.
 */
export async function signInWithGoogle(): Promise<User | null> {
  const instance = getFirebaseAuth()
  if (!instance) throw new Error('Firebase is not configured')
  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  try {
    const credential = await signInWithPopup(instance, provider)
    return credential.user
  } catch (error) {
    const code = firebaseErrorCode(error)
    if (code === 'auth/popup-blocked' || code === 'auth/operation-not-supported-in-this-environment') {
      await signInWithRedirect(instance, provider)
      return null
    }
    throw error
  }
}

/** Surfaces errors of a pending redirect sign-in (no-op otherwise). */
export async function consumeRedirectResult(): Promise<void> {
  const instance = getFirebaseAuth()
  if (instance) await getRedirectResult(instance)
}

/** Current Firebase ID token; Firebase refreshes it when it is about to expire. */
export async function getIdToken(forceRefresh = false): Promise<string | null> {
  const user = getFirebaseAuth()?.currentUser
  return user ? user.getIdToken(forceRefresh) : null
}

export async function firebaseSignOut(): Promise<void> {
  const instance = getFirebaseAuth()
  if (instance) await signOut(instance).catch(() => {})
}
