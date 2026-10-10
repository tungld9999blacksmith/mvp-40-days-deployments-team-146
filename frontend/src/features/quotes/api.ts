import { apiGet, apiRequest } from '@/shared/api/client'
import type { ApproveRequest, Quote, QuoteDisplayStatus, QuoteList, WorkshopQuoteDetail, WorkshopQuoteList } from './types'

const id = (quoteId: string) => encodeURIComponent(quoteId)

/** API-QT-01 — the backend builds the draft from the estimate; never send lines or prices (BR-1101). */
export async function createQuote(body: { userVehicleId: string; workshopId: string; odoMilestone: number }): Promise<Quote> {
  return (await apiRequest<Quote>('/quotes', { method: 'POST', body, timeoutMs: 15_000 })).data
}

/** API-QT-02 */
export function listMyQuotes(params: { unseenResult?: boolean; cursor?: string | null } = {}): Promise<QuoteList> {
  const search = new URLSearchParams()
  if (params.unseenResult) search.set('unseenResult', 'true')
  if (params.cursor) search.set('cursor', params.cursor)
  const query = search.toString()
  return apiGet<QuoteList>(`/quotes${query ? `?${query}` : ''}`, { timeoutMs: 10_000 })
}

/** API-QT-03 — opening a reviewed quote marks its result as seen. */
export function getQuote(quoteId: string): Promise<Quote> {
  return apiGet<Quote>(`/quotes/${id(quoteId)}`, { timeoutMs: 10_000 })
}

/** API-QT-04 — only after the owner's explicit confirmation (BR-1103). */
export async function submitQuote(quoteId: string, idempotencyKey: string): Promise<Quote> {
  const response = await apiRequest<Quote>(`/quotes/${id(quoteId)}/submit`, {
    method: 'POST',
    body: { confirm: true },
    headers: { 'Idempotency-Key': idempotencyKey },
    timeoutMs: 15_000,
  })
  return response.data
}

/** API-QT-05 — drafts only. */
export async function deleteQuote(quoteId: string): Promise<void> {
  await apiRequest<void>(`/quotes/${id(quoteId)}`, { method: 'DELETE', timeoutMs: 10_000 })
}

/** API-QT-11 — default `PENDING_APPROVAL`, longest waiting first. */
export function listWorkshopQuotes(status: Extract<QuoteDisplayStatus, 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'>): Promise<WorkshopQuoteList> {
  return apiGet<WorkshopQuoteList>(`/workshop-owner/quotes?status=${status}`, { timeoutMs: 10_000 })
}

/** API-QT-12 */
export function getWorkshopQuote(quoteId: string): Promise<WorkshopQuoteDetail> {
  return apiGet<WorkshopQuoteDetail>(`/workshop-owner/quotes/${id(quoteId)}`, { timeoutMs: 10_000 })
}

/** API-QT-13 — only changed lines are sent; the total is computed by the backend. */
export async function approveQuote(quoteId: string, body: ApproveRequest): Promise<WorkshopQuoteDetail> {
  return (await apiRequest<WorkshopQuoteDetail>(`/workshop-owner/quotes/${id(quoteId)}/approve`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

/** API-QT-14 — reason 10–500 characters (BR-1107). */
export async function rejectQuote(quoteId: string, reviewerNote: string): Promise<WorkshopQuoteDetail> {
  const response = await apiRequest<WorkshopQuoteDetail>(`/workshop-owner/quotes/${id(quoteId)}/reject`, {
    method: 'POST',
    body: { reviewerNote },
    timeoutMs: 15_000,
  })
  return response.data
}
