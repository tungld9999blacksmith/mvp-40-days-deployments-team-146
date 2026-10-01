import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ApiError } from '@/shared/api/client'
import { useWorkshopAuth } from '../context/WorkshopAuthContext'
import * as workshopApi from '../api'
import type { OperatingHour, WorkshopAttempt, WorkshopFailureReason, WorkshopOnboardingSnapshot, WorkshopSummary } from '../types'

export interface OperationsFormState {
  address: string
  latitude: string
  longitude: string
  hotline: string
  totalTechnicians: string
  emergencySlotsReserved: string
  operatingHours: OperatingHour[]
  consentGranted: boolean
}

export interface WorkshopOutcome {
  attempt: WorkshopAttempt | null
  failureReason: WorkshopFailureReason | null
  retryAfterSeconds: number | null
  workshop: WorkshopSummary | null
}

interface WorkshopOnboardingContextValue {
  snapshot: WorkshopOnboardingSnapshot | null
  snapshotError: ApiError | null
  loadingSnapshot: boolean
  loadSnapshot: () => Promise<WorkshopOnboardingSnapshot | null>
  operationsForm: OperationsFormState | null
  setOperationsForm: (form: OperationsFormState) => void
  outcome: WorkshopOutcome | null
  setOutcome: (outcome: WorkshopOutcome | null) => void
  focusField: string | null
  setFocusField: (field: string | null) => void
}

const WorkshopOnboardingContext = createContext<WorkshopOnboardingContextValue | null>(null)

export function WorkshopOnboardingProvider({ children }: { children: ReactNode }) {
  const { setOnboarding, setWorkshop } = useWorkshopAuth()
  const [snapshot, setSnapshot] = useState<WorkshopOnboardingSnapshot | null>(null)
  const [snapshotError, setSnapshotError] = useState<ApiError | null>(null)
  const [loadingSnapshot, setLoadingSnapshot] = useState(false)
  const [operationsForm, setOperationsForm] = useState<OperationsFormState | null>(null)
  const [outcome, setOutcome] = useState<WorkshopOutcome | null>(null)
  const [focusField, setFocusField] = useState<string | null>(null)
  const inflight = useRef<Promise<WorkshopOnboardingSnapshot | null> | null>(null)

  const loadSnapshot = useCallback(() => {
    if (inflight.current) return inflight.current
    setLoadingSnapshot(true)
    const promise = workshopApi
      .getOnboarding()
      .then(data => {
        setSnapshot(data)
        setSnapshotError(null)
        setOnboarding(data.onboarding)
        if (data.workshop) setWorkshop(data.workshop)
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
  }, [setOnboarding, setWorkshop])

  const value = useMemo(
    () => ({
      snapshot,
      snapshotError,
      loadingSnapshot,
      loadSnapshot,
      operationsForm,
      setOperationsForm,
      outcome,
      setOutcome,
      focusField,
      setFocusField,
    }),
    [snapshot, snapshotError, loadingSnapshot, loadSnapshot, operationsForm, outcome, focusField],
  )

  return <WorkshopOnboardingContext.Provider value={value}>{children}</WorkshopOnboardingContext.Provider>
}

export function useWorkshopOnboarding(): WorkshopOnboardingContextValue {
  const context = useContext(WorkshopOnboardingContext)
  if (!context) throw new Error('useWorkshopOnboarding must be used inside <WorkshopOnboardingProvider>')
  return context
}
