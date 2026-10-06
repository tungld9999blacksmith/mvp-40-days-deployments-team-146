import { apiGet, apiRequest } from '@/shared/api/client'
import type { Progress, Stage } from './types'

const id = (bookingId: string) => encodeURIComponent(bookingId)

/** API-PG-03 — owner timeline. */
export function getBookingProgress(bookingId: string): Promise<Progress> {
  return apiGet<Progress>(`/bookings/${id(bookingId)}/progress`, { timeoutMs: 10_000 })
}

/** API-PG-01 — Portal timeline + `nextStages`. */
export function getWorkshopProgress(bookingId: string): Promise<Progress> {
  return apiGet<Progress>(`/workshop-owner/bookings/${id(bookingId)}/progress`, { timeoutMs: 10_000 })
}

/** API-PG-02 — `expectedCurrentStage` guards against two tabs (EF-1302). */
export async function addProgressStage(
  bookingId: string,
  body: { stage: Stage; note?: string; expectedCurrentStage: Stage | null },
): Promise<Progress> {
  const response = await apiRequest<Progress>(`/workshop-owner/bookings/${id(bookingId)}/progress`, {
    method: 'POST',
    body,
    timeoutMs: 10_000,
  })
  return response.data
}
