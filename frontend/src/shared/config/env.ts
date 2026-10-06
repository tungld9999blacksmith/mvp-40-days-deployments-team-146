/** Runtime configuration read from Vite env variables (root .env, see .env.example). */

const env = import.meta.env

export const firebaseConfig = {
  apiKey: env.VITE_FIREBASE_API_KEY ?? '',
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN ?? '',
  projectId: env.VITE_FIREBASE_PROJECT_ID ?? '',
  appId: env.VITE_FIREBASE_APP_ID ?? '',
}

/** Firebase needs at least an API key, auth domain and project id to sign in. */
export const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId,
)

export const firebaseAuthEmulatorUrl = env.VITE_FIREBASE_AUTH_EMULATOR_URL ?? ''
export const DEMO_MODE = env.VITE_DEMO_MODE === 'true' || Boolean(firebaseAuthEmulatorUrl)

/** Policy versions must match the backend `CONSENT_POLICY_VERSION` settings. */
export const CONSENT_POLICY_VERSION = env.VITE_CONSENT_POLICY_VERSION || '2026-09'
export const WORKSHOP_CONSENT_POLICY_VERSION = env.VITE_WORKSHOP_CONSENT_POLICY_VERSION || 'WS-2026-09'

/** Chat transport: the backend SSE contract (API-CHAT-004) by default; `mock` works without a backend. */
export const CHAT_TRANSPORT: 'mock' | 'http' = env.VITE_CHAT_TRANSPORT === 'mock' ? 'mock' : 'http'
export const CHAT_WS_ENABLED = env.VITE_CHAT_WS_ENABLED === 'true'

/** Support channel is still undecided (open question in the FE specs). */
export const SUPPORT_URL = env.VITE_SUPPORT_URL ?? ''

/** UI demo uses the backend store, never the standalone browser mocks. */
export const API_MOCKS: 'off' | 'all' | 'demo' | string[] = (() => {
  const raw = (env.VITE_API_MOCKS ?? '').trim().toLowerCase()
  if (!raw || raw === 'off' || raw === 'false') return 'off'
  if (raw === 'all' || raw === 'demo') return raw
  return raw.split(',').map(value => value.trim()).filter(Boolean)
})()
export const isAuthConfigured = isFirebaseConfigured
