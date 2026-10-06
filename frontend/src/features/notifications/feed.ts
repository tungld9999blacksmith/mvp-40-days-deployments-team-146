import { formatDate, formatKm } from '@/shared/utils/format'
import type { BoardItem } from '@/features/workshop-board/types'
import type { NotificationItem } from './types'

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

/** Owner feed (API-NOTI-003) → list entry. */
export function toFeedEntry(item: NotificationItem): FeedEntry | null {
  const base = { id: item.id, at: item.occurredAt, unread: item.unread }
  if (item.kind === 'MAINTENANCE_REMINDER' && item.reminder) {
    const { level, odoMilestoneKm, resolved } = item.reminder
    return {
      ...base,
      tone: level === 'EXPIRED' || level === 'URGENT' ? 'warning' : 'info',
      title: REMINDER_TITLE[level],
      message: resolved
        ? `Mốc ${formatKm(odoMilestoneKm)} — đã có lịch hẹn cho mốc này.`
        : `Xe sắp tới mốc bảo dưỡng ${formatKm(odoMilestoneKm)}.`,
      action: resolved ? null : { label: 'Đặt lịch ngay', to: '/booking' },
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
  return null // unknown kind from a newer backend: skip rather than break the list
}

/** Workshop portal: bookings waiting for the workshop's confirmation (API-WB-01, no feed API for workshops). */
export function portalEntries(pending: BoardItem[]): FeedEntry[] {
  return pending.map(item => ({
    id: `booking:${item.bookingId}`,
    tone: 'warning',
    title: 'Lịch hẹn chờ xác nhận',
    message: `${item.customer.fullName} · ${item.vehicle.modelName} · ${item.timeSlot.slice(0, 5)} ${formatDate(item.bookingDate)}`,
    at: '',
    unread: true,
    action: { label: 'Xem lịch hẹn', to: `/technician/board/${encodeURIComponent(item.bookingId)}` },
  }))
}
