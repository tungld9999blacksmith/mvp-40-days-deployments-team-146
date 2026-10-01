import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { onAuthStateChanged } from 'firebase/auth'
import { configureApiClient, isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import { clearSessionCaches } from '@/shared/session/sessionCache'
import { track } from '@/shared/utils/track'
import type { AuthStatus, LoginError, SessionNotice } from '@/features/auth/context/AuthContext'
import {
  consumeRedirectResult,
  firebaseErrorCode,
  firebaseSignOut,
  getFirebaseAuth,
  getIdToken,
  isSignInCancelled,
  signInWithGoogle,
} from '@/features/auth/firebase'
import { clearPortal, getPortal, setPortal } from '@/features/auth/portal'
import * as workshopApi from '../api'
import type { WorkshopOnboardingState, WorkshopOwner, WorkshopSummary } from '../types'

interface WorkshopAuthContextValue {
  authStatus: AuthStatus
  owner: WorkshopOwner | null
  onboarding: WorkshopOnboardingState | null
  workshop: WorkshopSummary | null
  displayName: string
  lastLoginAt: string | null
  sessionNotice: SessionNotice
  loginError: LoginError | null
  bootError: ApiError | null
  isSigningIn: boolean
  signIn: () => Promise<void>
  retryBootstrap: () => void
  logout: () => Promise<boolean>
  setOnboarding: (onboarding: WorkshopOnboardingState) => void
  setWorkshop: (workshop: WorkshopSummary | null) => void
  clearLoginError: () => void
  expireSession: (notice?: SessionNotice) => void
}

const WorkshopAuthContext = createContext<WorkshopAuthContextValue | null>(null)

const SESSION_CHECK_INTERVAL_MS = 15 * 60 * 1000
const LOGIN_PATH = '/workshop/login'

function toLoginError(error: unknown): LoginError {
  if (isApiError(error)) return { code: error.code, message: error.message, traceId: error.traceId }
  return { code: firebaseErrorCode(error) ?? 'SIGN_IN_FAILED', message: '' }
}

function isTransient(error: unknown): boolean {
  return isApiError(error) && (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR || error.status >= 500)
}

/**
 * Workshop Portal session (US-013 FE §4.1): on restore, GET /oauth/session first
 * (detects revoked tokens), then POST /oauth/sign-in once — every sign-in call writes
 * a `login` audit log, so it is never repeated on navigation or tab focus.
 */
export function WorkshopAuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [authStatus, setAuthStatus] = useState<AuthStatus>('initializing')
  const [owner, setOwner] = useState<WorkshopOwner | null>(null)
  const [onboarding, setOnboarding] = useState<WorkshopOnboardingState | null>(null)
  const [workshop, setWorkshop] = useState<WorkshopSummary | null>(null)
  const [lastLoginAt, setLastLoginAt] = useState<string | null>(null)
  const [sessionNotice, setSessionNotice] = useState<SessionNotice>(null)
  const [loginError, setLoginError] = useState<LoginError | null>(null)
  const [bootError, setBootError] = useState<ApiError | null>(null)
  const [isSigningIn, setIsSigningIn] = useState(false)

  const inflight = useRef<{ uid: string; promise: Promise<void> } | null>(null)
  const syncedUid = useRef<string | null>(null)
  const manualSignIn = useRef(false)
  const expiring = useRef(false)
  const lastSessionCheck = useRef(0)

  const resetAccount = useCallback(() => {
    syncedUid.current = null
    setOwner(null)
    setOnboarding(null)
    setWorkshop(null)
  }, [])

  const expireSession = useCallback(
    (notice: SessionNotice = 'expired') => {
      if (expiring.current) return
      expiring.current = true
      if (notice === 'revoked') track('workshop_session_revoked_detected', { source: 'periodic' })
      void firebaseSignOut().finally(() => {
        clearSessionCaches()
        resetAccount()
        setSessionNotice(notice)
        setAuthStatus('signed-out')
        navigate(LOGIN_PATH, { replace: true })
        expiring.current = false
      })
    },
    [navigate, resetAccount],
  )

  const failSignIn = useCallback(
    async (error: unknown, manual: boolean) => {
      if (!manual && isTransient(error)) {
        setBootError(error as ApiError)
        return
      }
      await firebaseSignOut()
      resetAccount()
      if (isApiError(error) && error.status === 401) {
        setSessionNotice(error.code === 'TOKEN_REVOKED' ? 'revoked' : 'expired')
        if (error.code === 'TOKEN_REVOKED') track('workshop_session_revoked_detected', { source: 'startup' })
      } else {
        setLoginError(toLoginError(error))
        track('workshop_login_blocked', { errorCode: toLoginError(error).code })
      }
      setAuthStatus('signed-out')
    },
    [resetAccount],
  )

  const syncAccount = useCallback(
    (uid: string): Promise<void> => {
      if (inflight.current?.uid === uid) return inflight.current.promise
      const manual = manualSignIn.current
      const promise = (async () => {
        try {
          if (!manual) {
            // Restoring: detect a revoked session before signing in (AC-306).
            try {
              const session = await workshopApi.getSession()
              setLastLoginAt(session.lastLoginAt)
            } catch (error) {
              // 404 = no workshop account yet → sign-in creates it (AF-303).
              if (!isApiError(error, 'WORKSHOP_OWNER_NOT_REGISTERED')) throw error
            }
          }
          const { data } = await workshopApi.signIn()
          syncedUid.current = uid
          lastSessionCheck.current = Date.now()
          setPortal('workshop')
          setOwner(data.owner)
          setOnboarding(data.onboarding)
          setWorkshop(data.workshop)
          setBootError(null)
          setLoginError(null)
          setAuthStatus('signed-in')
          track(manual ? 'workshop_login_succeeded' : 'workshop_session_restored', {
            isNewOwner: data.isNewOwner,
            nextStep: data.onboarding.nextStep,
          })
        } catch (error) {
          await failSignIn(error, manual)
        } finally {
          manualSignIn.current = false
          inflight.current = null
          setIsSigningIn(false)
        }
      })()
      inflight.current = { uid, promise }
      return promise
    },
    [failSignIn],
  )

  useEffect(() => {
    configureApiClient({ getToken: getIdToken, onUnauthorized: () => expireSession('expired') })
  }, [expireSession])

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
        setAuthStatus(status => (status === 'signed-in' || status === 'initializing' ? 'signed-out' : status))
        return
      }
      // Only restore sessions that were opened through the Workshop Portal (no silent account creation).
      if (getPortal() !== 'workshop' && !manualSignIn.current) {
        setAuthStatus('signed-out')
        return
      }
      if (syncedUid.current === firebaseUser.uid) return
      void syncAccount(firebaseUser.uid)
    })
  }, [resetAccount, syncAccount])

  // Periodic session check (every 15 min while open, and on focus after ≥ 15 min) — US-013 FE §4.2.
  useEffect(() => {
    if (authStatus !== 'signed-in') return
    const check = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastSessionCheck.current < SESSION_CHECK_INTERVAL_MS) return
      lastSessionCheck.current = Date.now()
      workshopApi
        .getSession()
        .then(session => setOnboarding(session.onboarding))
        .catch(error => {
          if (!isApiError(error)) return
          if (error.status === 401) expireSession('revoked')
          else if (error.code === 'ACCOUNT_SUSPENDED' || error.code === 'ACCOUNT_INACTIVE') {
            setLoginError(toLoginError(error))
            expireSession(null)
          }
        })
    }
    const timer = window.setInterval(check, 60_000)
    document.addEventListener('visibilitychange', check)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [authStatus, expireSession])

  const signIn = useCallback(async () => {
    setLoginError(null)
    setSessionNotice(null)
    setIsSigningIn(true)
    manualSignIn.current = true
    setPortal('workshop')
    try {
      const firebaseUser = await signInWithGoogle()
      if (!firebaseUser) return
      syncedUid.current = null
      await syncAccount(firebaseUser.uid)
    } catch (error) {
      manualSignIn.current = false
      setIsSigningIn(false)
      if (isSignInCancelled(error)) return
      setLoginError(toLoginError(error))
    }
  }, [syncAccount])

  const retryBootstrap = useCallback(() => {
    const current = getFirebaseAuth()?.currentUser
    setBootError(null)
    if (current) void syncAccount(current.uid)
    else setAuthStatus('signed-out')
  }, [syncAccount])

  const logout = useCallback(async () => {
    let serverAck = false
    try {
      await workshopApi.logout()
      serverAck = true
    } catch (error) {
      serverAck = isApiError(error) && error.status === 401
    }
    await firebaseSignOut()
    clearPortal()
    clearSessionCaches()
    resetAccount()
    setSessionNotice(serverAck ? 'logged-out' : 'logged-out-offline')
    setAuthStatus('signed-out')
    track('workshop_logout_completed', { serverAck })
    navigate(LOGIN_PATH, { replace: true })
    return serverAck
  }, [navigate, resetAccount])

  const value = useMemo<WorkshopAuthContextValue>(
    () => ({
      authStatus,
      owner,
      onboarding,
      workshop,
      displayName: owner?.fullName || owner?.displayName || owner?.email || '',
      lastLoginAt,
      sessionNotice,
      loginError,
      bootError,
      isSigningIn,
      signIn,
      retryBootstrap,
      logout,
      setOnboarding,
      setWorkshop,
      clearLoginError: () => setLoginError(null),
      expireSession,
    }),
    [
      authStatus,
      owner,
      onboarding,
      workshop,
      lastLoginAt,
      sessionNotice,
      loginError,
      bootError,
      isSigningIn,
      signIn,
      retryBootstrap,
      logout,
      expireSession,
    ],
  )

  return <WorkshopAuthContext.Provider value={value}>{children}</WorkshopAuthContext.Provider>
}

export function useWorkshopAuth(): WorkshopAuthContextValue {
  const context = useContext(WorkshopAuthContext)
  if (!context) throw new Error('useWorkshopAuth must be used inside <WorkshopAuthProvider>')
  return context
}
