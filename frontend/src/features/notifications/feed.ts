import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import type { WorkshopQuoteItem } from '@/features/quotes/types'
import type { BoardItem } from '@/features/workshop-board/types'
import type { NotificationItem } from './types'
import { RESOLUTION_TEXT } from './reminderActions'

export type FeedTone = 'warning' | 'success' | 'info' | 'error'

/** What the notification list renders, whichever role and source it comes from. */
export interface FeedEntry {
  id: string
  tone: FeedTone
  title: string
  message: string
  at: string
  unread: boolean
  action: { label: string; to: string } | null
}

const REMINDER_TITLE: Record<NonNullable<NotificationItem['reminder']>['level'], string> = {
  EARLY: 'Sắp đến mốc bảo dưỡng',
  WARNING: 'Sắp đến hạn bảo dưỡng',
  URGENT: 'Gần tới hạn bảo dưỡng',
  EXPIRED: 'Đã quá hạn bảo dưỡng',
}

const at = (workshopName: string | null) => (workshopName ? ` tại ${workshopName}` : '')

function money(value: number | string | null): string | null {
  if (value === null) return null
  const amount = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(amount) ? formatVnd(amount) : null
}

/** Owner feed (API-NOTI-003) → list entry. */
export function toFeedEntry(item: NotificationItem): FeedEntry | null {
  const base = { id: item.id, at: item.occurredAt, unread: item.unread }
  if (item.kind === 'MAINTENANCE_REMINDER' && item.reminder) {
    const { level, odoMilestoneKm, resolved, resolutionReason } = item.reminder
    const detailed = resolutionReason !== undefined && item.id.startsWith('reminder:')
    return {
      ...base,
      tone: level === 'EXPIRED' || level === 'URGENT' ? 'warning' : 'info',
      title: REMINDER_TITLE[level],
      message: resolved
        ? `Mốc ${formatKm(odoMilestoneKm)} — ${RESOLUTION_TEXT[resolutionReason ?? ''] ?? (resolutionReason === undefined ? 'đã có lịch hẹn cho mốc này.' : 'lời nhắc đã đóng.')}`
        : `Xe ${level === 'EXPIRED' ? 'đã quá' : 'sắp tới'} mốc bảo dưỡng ${formatKm(odoMilestoneKm)}.`,
      action: detailed ? { label: 'Xem lời nhắc', to: `/notifications/reminders/${encodeURIComponent(item.id.slice('reminder:'.length))}` }
        : resolved ? null : { label: 'Đặt lịch ngay', to: '/booking' },
    }
  }
  if (item.kind === 'QUOTE_RESULT' && item.quote) {
    const { quoteId, status, approvedTotal, workshopName } = item.quote
    const total = money(approvedTotal)
    return {
      ...base,
      tone: status === 'APPROVED' ? 'success' : 'error',
      title: status === 'APPROVED' ? 'Báo giá đã được duyệt' : 'Báo giá chưa được duyệt',
      message:
        status === 'APPROVED'
          ? `Xưởng${at(workshopName)} đã duyệt báo giá${total ? `: ${total}` : ''}.`
          : `Xưởng${at(workshopName)} đã phản hồi báo giá. Xem lý do trong chi tiết.`,
      action: { label: 'Xem báo giá', to: `/quotes/${encodeURIComponent(quoteId)}` },
    }
  }
  if (item.kind === 'BOOKING_UPDATE' && item.booking) {
    const { bookingId, bookingCode, status, bookingDate, timeSlot, workshopName } = item.booking
    const when = `${timeSlot.slice(0, 5)} ${formatDate(bookingDate)}`
    const copy = {
      CONFIRMED: { tone: 'success' as const, title: 'Lịch hẹn đã được xác nhận', message: `${bookingCode} · ${when}${at(workshopName)}.` },
      CANCELLED: { tone: 'error' as const, title: 'Lịch hẹn đã bị huỷ', message: `${bookingCode} · ${when}${at(workshopName)}. Bạn có thể đặt lịch khác.` },
      COMPLETED: { tone: 'success' as const, title: 'Đã hoàn tất dịch vụ', message: `${bookingCode}${at(workshopName)} đã hoàn tất.` },
    }[status]
    return { ...base, ...copy, action: { label: 'Xem lịch hẹn', to: `/bookings/${encodeURIComponent(bookingId)}` } }
  }
  if (item.kind === 'BOOKING_REMINDER' && item.bookingReminder) {
    const { bookingId, bookingCode, bookingDate, timeSlot, workshopName } = item.bookingReminder
    return {
      ...base,
      tone: item.unread ? 'warning' : 'info',
      title: 'Nhắc lịch hẹn sắp tới',
      message: `${bookingCode} · ${timeSlot.slice(0, 5)} ${formatDate(bookingDate)}${at(workshopName)}.${item.unread ? ' Xác nhận bạn sẽ đến, hoặc đổi / huỷ nếu cần.' : ''}`,
      action: { label: 'Xem lịch hẹn', to: `/bookings/${encodeURIComponent(bookingId)}?src=REMINDER_24H` },
    }
  }
  if (item.kind === 'FOLLOW_UP' && item.followUp) {
    const { followUpId, workshopName } = item.followUp
    return {
      ...base,
      tone: 'info',
      title: 'Mời bạn đánh giá lần dịch vụ',
      message: `Lần dịch vụ${at(workshopName)} thế nào? Phản hồi của bạn giúp xưởng phục vụ tốt hơn.`,
      action: { label: 'Đánh giá', to: `/follow-ups/${encodeURIComponent(followUpId)}` },
    }
  }
  if (item.kind === 'BOOKING_LINE' && item.bookingLine) {
    const { bookingId, bookingCode, kind, status, itemName, price, workshopName } = item.bookingLine
    const amount = money(price)
    const ticket = `/bookings/${encodeURIComponent(bookingId)}`
    if (status === 'PROPOSED') {
      return {
        ...base,
        tone: 'warning',
        title: 'Cần bạn quyết định',
        message: `${workshopName ?? 'Xưởng'} ${kind === 'PACKAGE' ? 'đề xuất giá mới cho' : 'đề xuất thêm'} ${itemName}${amount ? ` · ${amount}` : ''} (${bookingCode}). Chỉ làm khi bạn đồng ý.`,
        action: { label: 'Mở phiếu để quyết định', to: ticket },
      }
    }
    return {
      ...base,
      tone: 'info',
      title: 'Xưởng đã xác nhận giá',
      message: `${itemName}${amount ? `: ${amount}` : ''} (${bookingCode})${at(workshopName)}.`,
      action: { label: 'Xem lịch hẹn', to: ticket },
    }
  }
  return null // unknown kind from a newer backend: skip rather than break the list
}

/**
 * Workshop portal: quotes waiting for review (API-QT-11) and bookings waiting for the workshop's
 * confirmation (API-WB-01) — there is no feed API for workshops.
 */
export function portalEntries(pending: BoardItem[], quotes: WorkshopQuoteItem[] = []): FeedEntry[] {
  const quoteEntries: FeedEntry[] = quotes.map(quote => ({
    id: `quote:${quote.quoteId}`,
    tone: quote.isWaitingLong ? 'warning' : 'info',
    title: quote.isWaitingLong ? 'Báo giá chờ duyệt quá 24 giờ' : 'Báo giá chờ duyệt',
    // API-QT-11 may return null customer name / model (deleted vehicle or user).
    message: [quote.customer.fullName, quote.modelName, `mốc ${formatKm(quote.odoMilestone)}`].filter(Boolean).join(' · '),
    at: quote.submittedAt ?? '',
    unread: quote.isWaitingLong,
    action: { label: 'Duyệt báo giá', to: `/technician/quote-review?quoteId=${encodeURIComponent(quote.quoteId)}` },
  }))
  const bookingEntries: FeedEntry[] = pending.map(item => ({
    id: `booking:${item.bookingId}`,
    tone: 'warning',
    title: 'Lịch hẹn chờ xác nhận',
    message: `${item.customer.fullName} · ${item.vehicle.modelName} · ${item.timeSlot.slice(0, 5)} ${formatDate(item.bookingDate)}`,
    at: '',
    unread: true,
    action: { label: 'Xem lịch hẹn', to: `/technician/board/${encodeURIComponent(item.bookingId)}` },
  }))
  return [...quoteEntries, ...bookingEntries]
}
