import type { QuoteListItem, WorkshopQuoteDetail } from './types'

/** Q-1105 — a pending quote waiting this long is flagged for the workshop. */
export const WAITING_LONG_HOURS = 24

/** BR-1109 — the owner has a reviewed quote (approved / rejected) not opened yet. */
export function hasUnseenResult(quote: Pick<QuoteListItem, 'status' | 'resultSeen'>): boolean {
  return (quote.status === 'APPROVED' || quote.status === 'REJECTED') && !quote.resultSeen
}

/** Whole hours since the owner submitted the quote (0 when not submitted). */
export function waitingHours(quote: Pick<WorkshopQuoteDetail, 'submittedAt'>, now: Date = new Date()): number {
  if (!quote.submittedAt) return 0
  return Math.max(0, Math.floor((now.getTime() - new Date(quote.submittedAt).getTime()) / 3_600_000))
}

export function isWaitingLong(quote: Pick<WorkshopQuoteDetail, 'status' | 'submittedAt'>, now: Date = new Date()): boolean {
  return quote.status === 'PENDING_APPROVAL' && waitingHours(quote, now) >= WAITING_LONG_HOURS
}

/** API-QT-12 returns the excerpt link only when the quote came from a conversation. */
export function hasConversation(quote: Pick<WorkshopQuoteDetail, 'conversationExcerptUrl'>): boolean {
  return Boolean(quote.conversationExcerptUrl)
}
