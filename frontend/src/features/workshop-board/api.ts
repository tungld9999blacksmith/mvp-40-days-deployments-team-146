import { apiGet, apiRequest } from '@/shared/api/client'
import type {
  BoardData,
  BoardDetail,
  BoardStatus,
  BookingSettings,
  CapacityData,
  CodeLookup,
  SlotBlockRequest,
  SlotBlockResult,
  TransitionRequest,
  TransitionResult,
} from './types'

const BASE = '/workshop-owner'
const id = (bookingId: string) => encodeURIComponent(bookingId)

/** API-WB-01 — bookings of the workshop in a date range; `summary` ignores the status filter. */
export function getBoard(params: { from: string; to: string; statuses: BoardStatus[]; q: string; signal?: AbortSignal }): Promise<BoardData> {
  const search = new URLSearchParams({ from: params.from, to: params.to })
  for (const status of params.statuses) search.append('status', status)
  if (params.q) search.set('q', params.q)
  return apiGet<BoardData>(`${BASE}/bookings?${search}`, { timeoutMs: 10_000, signal: params.signal })
}

/** API-WB-02 */
export function getBoardBooking(bookingId: string): Promise<BoardDetail> {
  return apiGet<BoardDetail>(`${BASE}/bookings/${id(bookingId)}`, { timeoutMs: 10_000 })
}

/** API-WB-03 — read only; check-in is a separate WB-04 after the owner confirms. */
export function lookupBookingCode(code: string): Promise<CodeLookup> {
  return apiGet<CodeLookup>(`${BASE}/bookings/by-code/${encodeURIComponent(code)}`, { timeoutMs: 10_000 })
}

/** API-WB-04 — never retried automatically (FE §12.3). */
export async function transitionBooking(bookingId: string, body: TransitionRequest): Promise<TransitionResult> {
  return (await apiRequest<TransitionResult>(`${BASE}/bookings/${id(bookingId)}/transitions`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

/** API-WB-05 */
export function getCapacity(from: string, days = 7): Promise<CapacityData> {
  return apiGet<CapacityData>(`${BASE}/capacity?from=${from}&days=${days}`, { timeoutMs: 10_000 })
}

/** API-WB-06 — absolute value; `0` removes the block. */
export async function saveSlotBlock(body: SlotBlockRequest): Promise<SlotBlockResult> {
  return (await apiRequest<SlotBlockResult>(`${BASE}/slot-blocks`, { method: 'PUT', body, timeoutMs: 10_000 })).data
}

/** API-WB-07 */
export function getBookingSettings(): Promise<BookingSettings> {
  return apiGet<BookingSettings>(`${BASE}/booking-settings`, { timeoutMs: 10_000 })
}

/** API-WB-08 */
export async function saveBookingSettings(confirmationMode: 'AUTO' | 'MANUAL'): Promise<BookingSettings> {
  return (await apiRequest<BookingSettings>(`${BASE}/booking-settings`, { method: 'PUT', body: { confirmationMode }, timeoutMs: 10_000 })).data
}
