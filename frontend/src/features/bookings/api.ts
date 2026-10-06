import { apiGet, apiRequest, rawRequest, toApiError } from '@/shared/api/client'
import type {
  AttendanceResult,
  AvailabilityData,
  Booking,
  BookingDetail,
  BookingSource,
  CancelHoldData,
  CancelResult,
  HoldRequest,
  LocationAnchor,
  MyBookingsPage,
  NearbyData,
} from './types'
import { toBookingDetail, type TicketDto } from './ticketAdapter'

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

// ---------------------------------------------------------------- us-033 / us-053

const bookingPath = (bookingId: string) => `/bookings/${encodeURIComponent(bookingId)}`

/** API-BR-01 — the ticket; `allowedActions` decides every button (FE never infers from time). */
export async function getBooking(bookingId: string, src?: BookingSource): Promise<BookingDetail> {
  return toBookingDetail(await apiGet<TicketDto>(`${bookingPath(bookingId)}${query({ src })}`, { timeoutMs: 10_000 }))
}

/** API-BT-01 — "Lịch của tôi". */
export function listMyBookings(scope: 'UPCOMING' | 'PAST', cursor: string | null = null): Promise<MyBookingsPage> {
  return apiGet<MyBookingsPage>(`/bookings${query({ scope, cursor, limit: 20 })}`, { timeoutMs: 10_000 })
}

/** API-BR-02 — no dialog: not destructive. */
export async function confirmAttendance(bookingId: string): Promise<AttendanceResult> {
  return (await apiRequest<AttendanceResult>(`${bookingPath(bookingId)}/attendance-confirmation`, { method: 'POST', timeoutMs: 10_000 })).data
}

/** API-BR-03 — only after the second confirmation (SCR-702); retries reuse the same key. */
export async function cancelBooking(
  bookingId: string,
  body: { source: BookingSource; reason?: string },
  idempotencyKey: string,
): Promise<CancelResult> {
  const response = await apiRequest<CancelResult>(`${bookingPath(bookingId)}/cancel`, {
    method: 'POST',
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    timeoutMs: 10_000,
  })
  return response.data
}

/** API-BT-03 — `/c/{code}` from the QR. */
export function resolveBookingCode(code: string): Promise<{ bookingId: string }> {
  return apiGet<{ bookingId: string }>(`/bookings/by-code/${encodeURIComponent(code.toUpperCase())}`, { timeoutMs: 10_000 })
}

/** API-BT-02 — PNG of the QR (for saving/sharing). */
export async function downloadBookingQr(bookingId: string): Promise<Blob> {
  const { response, requestId } = await rawRequest(`${bookingPath(bookingId)}/qr`, { headers: { Accept: 'image/png' }, timeoutMs: 10_000 })
  if (!response.ok) throw await toApiError(response, requestId)
  return response.blob()
}

/** API-BK-02 with `rescheduleBookingId` — slots of the same workshop; with `timeSlot` a RESCHEDULE token. */
export function getRescheduleAvailability(params: {
  workshopId: string
  bookingId: string
  date: string
  timeSlot?: string | null
  signal?: AbortSignal
}): Promise<AvailabilityData> {
  return apiGet<AvailabilityData>(
    `/workshops/${encodeURIComponent(params.workshopId)}/availability${query({
      date: params.date,
      timeSlot: params.timeSlot,
      rescheduleBookingId: params.bookingId,
      withAlternatives: true,
    })}`,
    { timeoutMs: 30_000, signal: params.signal },
  )
}

/** API-BT-04 — atomic: the old slot is released only when the new one is held (BR-1205). */
export async function rescheduleBooking(
  bookingId: string,
  body: { confirmationToken: string; source: BookingSource },
  idempotencyKey: string,
): Promise<BookingDetail> {
  const response = await apiRequest<TicketDto>(`${bookingPath(bookingId)}/reschedule`, {
    method: 'POST',
    body,
    headers: { 'Idempotency-Key': idempotencyKey },
    timeoutMs: 15_000,
  })
  return toBookingDetail(response.data)
}
