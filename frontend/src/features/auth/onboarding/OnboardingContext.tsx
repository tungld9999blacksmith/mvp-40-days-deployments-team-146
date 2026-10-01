import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ApiError } from '@/shared/api/client'
import { useAuth } from '../context/AuthContext'
import * as authApi from '../api'
import type {
  OnboardingSnapshot,
  OnboardingVehicle,
  OnboardingWarranty,
  VehicleModel,
  VerificationFailureReason,
  VerificationResult,
} from '../types'

export interface VehicleFormState {
  vin: string
  licensePlate: string
  modelId: string
  manufactureYear: string
  consentGranted: boolean
}

/** Outcome of the last API-005 call kept for SCR-005 / SCR-006. */
export interface VerificationOutcome {
  result: VerificationResult | null
  /** `ALREADY_LINKED` (409) and attempts exceeded (429) are not in `result`. */
  failureReason: VerificationFailureReason | null
  remainingAttempts: number | null
  retryAfterSeconds: number | null
  vehicle: OnboardingVehicle | null
  warranties: OnboardingWarranty[]
}

interface OnboardingContextValue {
  snapshot: OnboardingSnapshot | null
  snapshotError: ApiError | null
  loadingSnapshot: boolean
  loadSnapshot: () => Promise<OnboardingSnapshot | null>
  vehicleForm: VehicleFormState | null
  setVehicleForm: (form: VehicleFormState) => void
  outcome: VerificationOutcome | null
  setOutcome: (outcome: VerificationOutcome | null) => void
  models: VehicleModel[] | null
  setModels: (models: VehicleModel[]) => void
  /** Field to highlight when coming back from SCR-006 (`vin`, `licensePlate`, `modelId`, `nationalId`). */
  focusField: string | null
  setFocusField: (field: string | null) => void
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { setOnboarding } = useAuth()
  const [snapshot, setSnapshot] = useState<OnboardingSnapshot | null>(null)
  const [snapshotError, setSnapshotError] = useState<ApiError | null>(null)
  const [loadingSnapshot, setLoadingSnapshot] = useState(false)
  const [vehicleForm, setVehicleForm] = useState<VehicleFormState | null>(null)
  const [outcome, setOutcome] = useState<VerificationOutcome | null>(null)
  const [models, setModels] = useState<VehicleModel[] | null>(null)
  const [focusField, setFocusField] = useState<string | null>(null)
  const inflight = useRef<Promise<OnboardingSnapshot | null> | null>(null)

  /** API-002 — also keeps AuthContext.onboarding in sync. */
  const loadSnapshot = useCallback(() => {
    if (inflight.current) return inflight.current
    setLoadingSnapshot(true)
    const promise = authApi
      .getOnboarding()
      .then(data => {
        setSnapshot(data)
        setSnapshotError(null)
        setOnboarding(data.onboarding)
        return data
      })
      .catch((error: ApiError) => {
        setSnapshotError(error)
        return null
      })
      .finally(() => {
        setLoadingSnapshot(false)
        inflight.current = null
      })
    inflight.current = promise
    return promise
  }, [setOnboarding])

  const value = useMemo(
    () => ({
      snapshot,
      snapshotError,
      loadingSnapshot,
      loadSnapshot,
      vehicleForm,
      setVehicleForm,
      outcome,
      setOutcome,
      models,
      setModels,
      focusField,
      setFocusField,
    }),
    [snapshot, snapshotError, loadingSnapshot, loadSnapshot, vehicleForm, outcome, models, focusField],
  )

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>
}

export function useOnboarding(): OnboardingContextValue {
  const context = useContext(OnboardingContext)
  if (!context) throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  return context
}
