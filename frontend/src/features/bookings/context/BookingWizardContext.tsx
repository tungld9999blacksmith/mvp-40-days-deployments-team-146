import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { VehicleSummary } from '@/features/vehicles/types'
import type { LocationAnchor, NearbyWorkshop } from '../types'

/** Summary card data: only ever kept in memory (FE §6 — never localStorage). */
export interface SummaryCard {
  workshopId: string
  date: string
  timeSlot: string
  confirmationToken: string
  /** epoch ms, estimated from the BK-02 answer time */
  expiresAt: number
  /** One key per token; a retry of the same Confirm reuses it (FE §6). */
  idempotencyKey: string
}

export interface BookingParams {
  proposalId: string | null
  workshopId: string | null
  date: string | null
  timeSlot: string | null
  odoMilestone: number | null
  quoteId: string | null
}

interface BookingWizardValue {
  vehicle: VehicleSummary
  params: BookingParams
  /** Search string for another step, keeping `odoMilestone` / `quoteId` (source of truth = query). */
  searchFor: (overrides: Partial<Record<keyof BookingParams, string | number | null>>) => string
  anchor: LocationAnchor
  setAnchor: (anchor: LocationAnchor) => void
  rememberWorkshops: (workshops: NearbyWorkshop[]) => void
  workshopById: (workshopId: string | null) => NearbyWorkshop | null
  card: SummaryCard | null
  setCard: (card: SummaryCard | null) => void
  note: string
  setNote: (note: string) => void
  /** epoch ms of the first wizard screen, for `booking_confirmed.secondsFromStart`. */
  startedAt: number
}

const BookingWizardContext = createContext<BookingWizardValue | null>(null)

function readNumber(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value)) return null
  return Number(value)
}

export function BookingWizardProvider({ vehicle, children }: { vehicle: VehicleSummary; children: ReactNode }) {
  const [searchParams] = useSearchParams()
  const [anchor, setAnchor] = useState<LocationAnchor>(null)
  const [card, setCard] = useState<SummaryCard | null>(null)
  const [note, setNote] = useState('')
  const [workshops, setWorkshops] = useState<Record<string, NearbyWorkshop>>({})
  const startedAt = useRef(Date.now()).current

  const params = useMemo<BookingParams>(
    () => ({
      proposalId: searchParams.get('proposalId'),
      workshopId: searchParams.get('workshopId'),
      date: searchParams.get('date'),
      timeSlot: searchParams.get('timeSlot'),
      odoMilestone: readNumber(searchParams.get('odoMilestone')),
      quoteId: searchParams.get('quoteId'),
    }),
    [searchParams],
  )

  const searchFor = useCallback<BookingWizardValue['searchFor']>(
    overrides => {
      const next = new URLSearchParams()
      const merged: Record<string, string | number | null> = { ...params, ...overrides }
      for (const key of ['proposalId', 'workshopId', 'date', 'timeSlot', 'odoMilestone', 'quoteId'] as const) {
        const value = merged[key]
        if (value !== null && value !== undefined && value !== '') next.set(key, String(value))
      }
      const text = next.toString()
      return text ? `?${text}` : ''
    },
    [params],
  )

  const rememberWorkshops = useCallback((list: NearbyWorkshop[]) => {
    setWorkshops(previous => {
      const next = { ...previous }
      for (const workshop of list) next[workshop.workshopId] = workshop
      return next
    })
  }, [])

  const workshopById = useCallback(
    (workshopId: string | null) => (workshopId ? workshops[workshopId] ?? null : null),
    [workshops],
  )

  const value = useMemo<BookingWizardValue>(
    () => ({
      vehicle,
      params,
      searchFor,
      anchor,
      setAnchor,
      rememberWorkshops,
      workshopById,
      card,
      setCard,
      note,
      setNote,
      startedAt,
    }),
    [vehicle, params, searchFor, anchor, rememberWorkshops, workshopById, card, note, startedAt],
  )

  return <BookingWizardContext.Provider value={value}>{children}</BookingWizardContext.Provider>
}

export function useBookingWizard(): BookingWizardValue {
  const value = useContext(BookingWizardContext)
  if (!value) throw new Error('useBookingWizard must be used inside BookingWizardProvider')
  return value
}
