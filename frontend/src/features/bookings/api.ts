import { apiGet, apiRequest } from '@/shared/api/client'
import type { AvailabilityData, Booking, CancelHoldData, HoldRequest, LocationAnchor, NearbyData } from './types'

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** API-BK-01 — active workshops near the anchor; with `date` + `timeSlot` also the slot availability. */
export function getNearbyWorkshops(params: {
  anchor: LocationAnchor
  userVehicleId: string
  date?: string | null
  timeSlot?: string | null
}): Promise<NearbyData> {
  const { anchor } = params
  return apiGet<NearbyData>(
    `/workshops/nearby${query({
      query: anchor?.kind === 'query' ? anchor.query : null,
      lat: anchor?.kind === 'coords' ? anchor.lat : null,
      lng: anchor?.kind === 'coords' ? anchor.lng : null,
      userVehicleId: params.userVehicleId,
      date: params.date,
      timeSlot: params.date ? params.timeSlot : null,
    })}`,
    { timeoutMs: 10_000 },
  )
}

/** API-BK-02 — slots of a day; with `timeSlot` also `requested` (+ `confirmationToken` when free). */
export function getAvailability(params: {
  workshopId: string
  date: string
  timeSlot?: string | null
  withAlternatives?: boolean
  signal?: AbortSignal
}): Promise<AvailabilityData> {
  return apiGet<AvailabilityData>(
    `/workshops/${encodeURIComponent(params.workshopId)}/availability${query({
      date: params.date,
      timeSlot: params.timeSlot,
      withAlternatives: params.withAlternatives ?? true,
    })}`,
    // The backend answers slowly (one capacity query per slot): allow a generous timeout.
    { timeoutMs: 30_000, signal: params.signal },
  )
}

/** API-BK-03 — only ever called from the owner's "Xác nhận" (AC-FE-401). */
export async function createBooking(body: HoldRequest, idempotencyKey: string): Promise<Booking> {
  const response = await apiRequest<Booking>('/bookings', {
    method: 'POST',
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    timeoutMs: 15_000,
  })
  return response.data
}

/** API-BK-04 — cancel the hold within the owner's window (BR-010). */
export async function cancelHold(bookingId: string): Promise<CancelHoldData> {
  const response = await apiRequest<CancelHoldData>(`/bookings/${encodeURIComponent(bookingId)}/hold`, {
    method: 'DELETE',
    timeoutMs: 10_000,
  })
  return response.data
}
