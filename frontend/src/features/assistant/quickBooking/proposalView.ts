import type { BadgeTone } from '@/shared/ui/Badge'
import { formatNumber } from '@/shared/utils/format'
import type { BookingProposalCard, MessageDto, ProposalBooking, ProposalStatus } from '../types'

/** Exact label of the suggestion chip (us-061 AC-1501). */
export const QUICK_BOOKING_LABEL = 'Đặt lịch bảo dưỡng nhanh'

export type ProposalAction = 'confirm' | 'revise' | 'cancel'

export interface ProposalView {
  status: ProposalStatus
  badge: { tone: BadgeTone; label: string }
  /** Booking code, only once the booking is confirmed (BR-1512). */
  code: string | null
  note: string | null
  /** "1,8 km" — only from a real distance (BR-1506). */
  distanceText: string | null
  areaText: string | null
  actions: ProposalAction[]
  canRetry: boolean
  ticketHref: string | null
}

const BOOKING_BADGES: Record<string, { tone: BadgeTone; label: string }> = {
  CONFIRMED: { tone: 'success', label: 'Đã xác nhận' },
  PENDING: { tone: 'warning', label: 'Chờ xưởng xác nhận' },
  CHECKED_IN: { tone: 'success', label: 'Đã check-in' },
  IN_PROGRESS: { tone: 'success', label: 'Đang bảo dưỡng' },
  COMPLETED: { tone: 'success', label: 'Đã hoàn tất' },
  CANCELLED: { tone: 'neutral', label: 'Lịch hẹn đã huỷ' },
}

const PROPOSAL_BADGES: Record<Exclude<ProposalStatus, 'CONFIRMED'>, { tone: BadgeTone; label: string }> = {
  PROPOSED: { tone: 'neutral', label: 'Chờ bạn xác nhận' },
  CANCELLED: { tone: 'neutral', label: 'Đã hủy đề xuất' },
  SUPERSEDED: { tone: 'neutral', label: 'Đã thay bằng đề xuất mới' },
  EXPIRED: { tone: 'neutral', label: 'Đề xuất đã hết hạn' },
}

export function formatDistance(km: number): string {
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(km)} km`
}

/** A PROPOSED card past `expiresAt` reads as EXPIRED without waiting for a reload. */
export function effectiveStatus(card: BookingProposalCard, now: Date = new Date()): ProposalStatus {
  if (card.status === 'PROPOSED' && new Date(card.expiresAt).getTime() <= now.getTime()) return 'EXPIRED'
  return card.status ?? 'PROPOSED'
}

/** Everything the proposal card shows, derived from the backend card only (FE spec §2.7). */
export function proposalView(card: BookingProposalCard, now: Date = new Date()): ProposalView {
  const status = effectiveStatus(card, now)
  const booking = status === 'CONFIRMED' ? card.booking : null
  const badge = booking
    ? BOOKING_BADGES[booking.status] ?? { tone: 'neutral' as BadgeTone, label: booking.status }
    : status === 'CONFIRMED'
      ? { tone: 'success' as BadgeTone, label: 'Đã đặt lịch' }
      : PROPOSAL_BADGES[status]
  const distance = card.primary.distanceKm
  return {
    status,
    badge,
    code: booking?.bookingCode ?? null,
    note: noteFor(status, booking),
    distanceText: distance !== null && distance !== undefined ? formatDistance(distance) : null,
    areaText: distance === null || distance === undefined ? card.locationLabel : null,
    actions: status === 'PROPOSED' ? ['confirm', 'revise', 'cancel'] : [],
    canRetry: status === 'EXPIRED',
    ticketHref: booking ? `/bookings/${encodeURIComponent(booking.bookingId)}` : null,
  }
}

function noteFor(status: ProposalStatus, booking: ProposalBooking | null): string | null {
  if (status === 'PROPOSED') return 'Đề xuất giữ trong 30 phút, chưa giữ chỗ. Lịch chỉ được tạo khi bạn bấm Xác nhận.'
  if (booking?.status === 'PENDING') return 'Xưởng xác nhận trong tối đa 12 giờ; mã đặt lịch có sau khi xưởng xác nhận.'
  return null
}

/** "350.000 ₫" */
export function formatMoney(value: string | number): string {
  return `${formatNumber(Number(value))} ₫`
}

/**
 * Messages whose BOOKING_PROPOSAL card is `proposalId`, with `patch` applied — ready for the
 * reducer's `merge` (same id ⇒ replaced).
 */
export function patchProposalCard(
  messages: MessageDto[],
  proposalId: string,
  patch: Partial<Pick<BookingProposalCard, 'status' | 'booking'>>,
): MessageDto[] {
  return messages
    .filter(message => message.card?.type === 'BOOKING_PROPOSAL' && message.card.proposalId === proposalId)
    .map(message => ({ ...message, card: { ...(message.card as object), ...patch } as MessageDto['card'] }))
}
