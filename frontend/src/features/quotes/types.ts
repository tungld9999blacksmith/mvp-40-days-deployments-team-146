/** FEAT-QUOTE-001 types — API Spec us-049 (API-QT-01 → 05, 11 → 14). */

export type QuoteDisplayStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'MODIFIED' | 'EXPIRED' | 'REJECTED'

export interface QuoteItem {
  quoteItemId: string
  itemCode: string
  itemName: string
  covered: boolean
  priceSource: 'WORKSHOP_PRICE' | 'REFERENCE_PRICE' | null
  estimatedPrice: number
  approvedPrice: number | null
  reviewerNote: string | null
}

/** API-QT-03 (owner) — also the base of the Portal detail. */
export interface Quote {
  quoteId: string
  status: string
  displayStatus: QuoteDisplayStatus
  workshop: { workshopId: string; name: string }
  userVehicleId: string
  odoMilestone: number
  items: QuoteItem[]
  estimatedTotal: number
  approvedTotal: number | null
  priceLabel: string
  createdAt: string
  submittedAt: string | null
  reviewedAt: string | null
  expiresAt: string | null
  reviewerNote: string | null
  bookingId: string | null
  canAttachToBooking: boolean
  /** `QUOTE_DRAFT_TTL_DAYS` after creation, only for drafts. */
  draftExpiresAt?: string | null
}

/** API-QT-02 row: the quote summary without lines; `resultSeen` drives the BR-1109 badge. */
export interface QuoteListItem extends Omit<Quote, 'items' | 'reviewerNote' | 'bookingId' | 'draftExpiresAt'> {
  resultSeen: boolean
}

export interface QuoteList {
  items: QuoteListItem[]
  nextCursor: string | null
}

/** API-QT-11 row. */
export interface WorkshopQuoteItem {
  quoteId: string
  displayStatus: QuoteDisplayStatus
  customer: { fullName: string; phone: string }
  modelName: string
  plateNumber: string
  odoMilestone: number
  estimatedTotal: number
  approvedTotal: number | null
  submittedAt: string | null
  waitingHours: number
  isWaitingLong: boolean
  hasConversation: boolean
}

export interface WorkshopQuoteList {
  items: WorkshopQuoteItem[]
  summary?: { PENDING_APPROVAL: number; APPROVED: number; REJECTED: number }
  nextCursor: string | null
}

/** API-QT-12 — no VIN, CCCD or email. */
export interface WorkshopQuoteDetail extends Quote {
  customer: { fullName: string; phone: string }
  modelName: string
  plateNumber: string
  conversationExcerptUrl: string | null
}

export interface ApproveRequest {
  validityDays: number
  reviewerNote?: string
  items: { quoteItemId: string; approvedPrice: number; note?: string }[]
}
