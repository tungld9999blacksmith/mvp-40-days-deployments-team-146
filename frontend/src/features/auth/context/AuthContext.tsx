import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { onAuthStateChanged } from 'firebase/auth'
import { configureApiClient, isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import { clearSessionCaches } from '@/shared/session/sessionCache'
import { track } from '@/shared/utils/track'
import {
  consumeRedirectResult,
  firebaseErrorCode,
  firebaseSignOut,
  getFirebaseAuth,
  getIdToken,
  isSignInCancelled,
  signInWithGoogle,
} from '../firebase'
import { clearPortal, getPortal, setPortal } from '../portal'
import * as authApi from '../api'
import type { OnboardingState, SignInUser } from '../types'

export type AuthStatus = 'initializing' | 'signed-out' | 'signed-in'

/** Banner shown on the login screen after the session ended (US-005 FE §4.4). */
export type SessionNotice = 'expired' | 'revoked' | 'logged-out' | 'logged-out-offline' | null

/** Error shown on the login screen (SCR-103 or general error). */
export interface LoginError {
  code: string
  message: string
  traceId?: string | null
}

interface AuthContextValue {
  authStatus: AuthStatus
  user: SignInUser | null
  onboarding: OnboardingState | null
  displayName: string
  sessionNotice: SessionNotice
  loginError: LoginError | null
  /** Restoring the session failed for a transient reason (network, 5xx); Splash offers retry. */
  bootError: ApiError | null
  isSigningIn: boolean
  isLoggingOut: boolean
  signIn: () => Promise<void>
  retryBootstrap: () => void
  logout: () => Promise<boolean>
  setOnboarding: (onboarding: OnboardingState) => void
  clearLoginError: () => void
  /** Ends the local session (401 after refresh, revoked token). */
  expireSession: (notice?: SessionNotice) => void
  rememberReturnTo: (path: string) => void
  consumeReturnTo: () => string | null
}

const AuthContext = createContext<AuthContextValue | null>(null)

const SESSION_CHECK_INTERVAL_MS = 15 * 60 * 1000

function toLoginError(error: unknown): LoginError {
  if (isApiError(error)) return { code: error.code, message: error.message, traceId: error.traceId }
  const code = firebaseErrorCode(error)
  return { code: code ?? 'SIGN_IN_FAILED', message: '' }
}

function isTransient(error: unknown): boolean {
  return isApiError(error) && (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR || error.status >= 500)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [authStatus, setAuthStatus] = useState<AuthStatus>('initializing')
  const [user, setUser] = useState<SignInUser | null>(null)
  const [onboarding, setOnboardingState] = useState<OnboardingState | null>(null)
  const [sessionNotice, setSessionNotice] = useState<SessionNotice>(null)
  const [loginError, setLoginError] = useState<LoginError | null>(null)
  const [bootError, setBootError] = useState<ApiError | null>(null)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  const inflight = useRef<{ uid: string; promise: Promise<void> } | null>(null)
  const syncedUid = useRef<string | null>(null)
  const manualSignIn = useRef(false)
  const expiring = useRef(false)
  const returnTo = useRef<string | null>(null)
  const lastSessionCheck = useRef(0)

  const resetAccount = useCallback(() => {
    syncedUid.current = null
    setUser(null)
    setOnboardingState(null)
  }, [])

  const expireSession = useCallback(
    (notice: SessionNotice = 'expired') => {
      if (expiring.current) return
      expiring.current = true
      const { pathname, search } = window.location
      if (pathname !== '/' && !pathname.startsWith('/onboarding')) returnTo.current = pathname + search
      track('session_expired', { source: notice === 'revoked' ? 'session-check' : 'api-401' })
      void firebaseSignOut().finally(() => {
        clearSessionCaches()
        resetAccount()
        setSessionNotice(notice)
        setAuthStatus('signed-out')
        navigate('/', { replace: true })
        expiring.current = false
      })
    },
    [navigate, resetAccount],
  )

  /** API-001: sync the account for the signed-in Firebase user. */
  const syncAccount = useCallback(
    (uid: string): Promise<void> => {
      if (inflight.current?.uid === uid) return inflight.current.promise
      const manual = manualSignIn.current
      const promise = (async () => {
        try {
          const { data } = await authApi.signIn()
          syncedUid.current = uid
          lastSessionCheck.current = Date.now()
          setPortal('owner')
          setUser(data.user)
          setOnboardingState(data.onboarding)
          setBootError(null)
          setLoginError(null)
          setAuthStatus('signed-in')
          track(manual ? 'login_succeeded' : 'session_restored', {
            isNewUser: data.isNewUser,
            nextStep: data.onboarding.nextStep,
          })
        } catch (error) {
          if (!manual && isTransient(error)) {
            // Keep the Firebase session; Splash shows a retry (US-005 FE §4.5).
            setBootError(error as ApiError)
            return
          }
          await firebaseSignOut()
          resetAccount()
          if (isApiError(error) && error.status === 401) {
            setSessionNotice('expired')
          } else {
            setLoginError(toLoginError(error))
            track(manual ? 'login_failed' : 'login_blocked', { errorCode: toLoginError(error).code })
          }
          setAuthStatus('signed-out')
        } finally {
          manualSignIn.current = false
          inflight.current = null
          setIsSigningIn(false)
        }
      })()
      inflight.current = { uid, promise }
      return promise
    },
    [resetAccount],
  )

  // Wire the API client to this provider.
  useEffect(() => {
    configureApiClient({ getToken: getIdToken, onUnauthorized: () => expireSession('expired') })
  }, [expireSession])

  // Restore the Firebase session (auto-login, US-007).
  useEffect(() => {
    const auth = getFirebaseAuth()
    if (!auth) {
      setAuthStatus('signed-out')
      return
    }
    consumeRedirectResult().catch(error => {
      if (!isSignInCancelled(error)) setLoginError(toLoginError(error))
    })
    return onAuthStateChanged(auth, firebaseUser => {
      if (!firebaseUser) {
        resetAccount()
        setAuthStatus(status => (status === 'initializing' || status === 'signed-in' ? 'signed-out' : status))
        return
      }
      // The session belongs to the Workshop Portal: do not create an owner account from it.
      if (getPortal() === 'workshop' && !manualSignIn.current) {
        setAuthStatus('signed-out')
        return
      }
      if (syncedUid.current === firebaseUser.uid) return
      void syncAccount(firebaseUser.uid)
    })
  }, [resetAccount, syncAccount])

  // Session check with revocation (API-102) when the tab comes back after ≥ 15 min.
  useEffect(() => {
    if (authStatus !== 'signed-in') return
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastSessionCheck.current < SESSION_CHECK_INTERVAL_MS) return
      lastSessionCheck.current = Date.now()
      authApi.getProfile().catch(error => {
        if (!isApiError(error)) return
        if (error.status === 401) expireSession('revoked')
        else if (error.code === 'ACCOUNT_SUSPENDED' || error.code === 'ACCOUNT_INACTIVE') {
          setLoginError(toLoginError(error))
          expireSession(null)
        }
      })
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [authStatus, expireSession])

  const signIn = useCallback(async () => {
    setLoginError(null)
    setSessionNotice(null)
    setIsSigningIn(true)
    manualSignIn.current = true
    setPortal('owner')
    track('login_google_clicked')
    try {
      const firebaseUser = await signInWithGoogle()
      if (!firebaseUser) return // redirect flow: the page reloads
      await syncAccount(firebaseUser.uid)
    } catch (error) {
      manualSignIn.current = false
      setIsSigningIn(false)
      if (isSignInCancelled(error)) return
      setLoginError(toLoginError(error))
      track('login_failed', { errorCode: toLoginError(error).code })
    }
  }, [syncAccount])

  const retryBootstrap = useCallback(() => {
    const current = getFirebaseAuth()?.currentUser
    setBootError(null)
    if (current) void syncAccount(current.uid)
    else setAuthStatus('signed-out')
  }, [syncAccount])

  /** US-005 FE §4.7 — API-101 first, then always sign out locally. Returns server ack. */
  const logout = useCallback(async () => {
    setIsLoggingOut(true)
    track('logout_confirmed')
    let serverAck = false
    try {
      await authApi.logout()
      serverAck = true
    } catch (error) {
      serverAck = isApiError(error) && error.status === 401
    }
    await firebaseSignOut()
    clearPortal()
    clearSessionCaches()
    resetAccount()
    returnTo.current = null
    setSessionNotice(serverAck ? 'logged-out' : 'logged-out-offline')
    setAuthStatus('signed-out')
    setIsLoggingOut(false)
    track('logout_completed', { serverAck })
    navigate('/', { replace: true })
    return serverAck
  }, [navigate, resetAccount])

  const value = useMemo<AuthContextValue>(
    () => ({
      authStatus,
      user,
      onboarding,
      displayName: user?.fullName || user?.displayName || user?.email || '',
      sessionNotice,
      loginError,
      bootError,
      isSigningIn,
      isLoggingOut,
      signIn,
      retryBootstrap,
      logout,
      setOnboarding: setOnboardingState,
      clearLoginError: () => setLoginError(null),
      expireSession,
      rememberReturnTo: (path: string) => {
        returnTo.current = path
      },
      consumeReturnTo: () => {
        const path = returnTo.current
        returnTo.current = null
        return path
      },
    }),
    [
      authStatus,
      user,
      onboarding,
      sessionNotice,
      loginError,
      bootError,
      isSigningIn,
      isLoggingOut,
      signIn,
      retryBootstrap,
      logout,
      expireSession,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
