/** Derived quote status (us-049 API §4) — shared by the quote, booking and Board mocks. */
import { getDb, type MockQuote } from './db'

export type DisplayStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'MODIFIED' | 'EXPIRED' | 'REJECTED'

export function displayStatusOf(quote: MockQuote): DisplayStatus {
  switch (quote.status) {
    case 'draft':
      return 'DRAFT'
    case 'pending_approval':
      return 'PENDING_APPROVAL'
    case 'rejected':
      return 'REJECTED'
    case 'approved': {
      if (quote.expiresAt && Date.now() >= new Date(quote.expiresAt).getTime()) return 'EXPIRED'
      return quote.items.some(item => item.approvedPrice !== null && item.approvedPrice !== item.estimatedPrice) ? 'MODIFIED' : 'APPROVED'
    }
  }
}

export function priceLabelOf(quote: MockQuote): string {
  const status = displayStatusOf(quote)
  if (status === 'APPROVED' || status === 'MODIFIED') return 'Báo giá đã duyệt'
  if (status === 'EXPIRED') return 'Đã hết hiệu lực'
  return 'Chi phí ước tính'
}

export function canAttachToBooking(quote: MockQuote): boolean {
  const status = displayStatusOf(quote)
  if (status !== 'APPROVED' && status !== 'MODIFIED') return false
  if (!quote.bookingId) return true
  const booking = getDb().bookings.find(item => item.bookingId === quote.bookingId)
  return !booking || booking.status === 'cancelled'
}
