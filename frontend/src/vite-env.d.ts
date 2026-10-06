/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FIREBASE_API_KEY?: string
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string
  readonly VITE_FIREBASE_PROJECT_ID?: string
  readonly VITE_FIREBASE_APP_ID?: string
  readonly VITE_FIREBASE_AUTH_EMULATOR_URL?: string
  readonly VITE_CONSENT_POLICY_VERSION?: string
  readonly VITE_WORKSHOP_CONSENT_POLICY_VERSION?: string
  readonly VITE_CHAT_TRANSPORT?: 'mock' | 'http'
  readonly VITE_CHAT_WS_ENABLED?: string
  readonly VITE_SUPPORT_URL?: string
  /** `off` / `all` (default) / comma list of mock groups — see src/mocks/server/index.ts */
  readonly VITE_API_MOCKS?: string
  /** `true` ⇒ demo mode: no backend, no Firebase, everything mocked (same as `vite --mode demo`). */
  readonly VITE_DEMO_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
