/** Vietnamese labels of booking statuses, reasons and sources — owner app and Workshop Portal. */
import type { BadgeTone } from '@/shared/ui/Badge'

export const BOOKING_STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  PENDING: { label: 'Chờ xưởng xác nhận', tone: 'warning' },
  CONFIRMED: { label: 'Đã xác nhận', tone: 'success' },
  CHECKED_IN: { label: 'Đã check-in', tone: 'success' },
  IN_PROGRESS: { label: 'Đang làm', tone: 'warning' },
  COMPLETED: { label: 'Hoàn tất', tone: 'neutral' },
  CANCELLED: { label: 'Đã huỷ', tone: 'error' },
}

export function bookingStatusLabel(status: string): string {
  return BOOKING_STATUS[status.toUpperCase()]?.label ?? status
}

/** Workshop Portal wording: the workshop itself is the one confirming. */
export const PORTAL_BOOKING_STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  ...BOOKING_STATUS,
  PENDING: { label: 'Chờ xác nhận', tone: 'warning' },
}

export const REASON_LABEL: Record<string, string> = {
  FULLY_BOOKED: 'Đã kín lịch',
  NOT_SUPPORTED_SERVICE: 'Không hỗ trợ hạng mục',
  WORKSHOP_UNAVAILABLE: 'Xưởng bận đột xuất',
  NO_SHOW: 'Khách không đến',
  CUSTOMER_REQUEST: 'Khách yêu cầu huỷ',
  CONFIRM_DEADLINE_PASSED: 'Xưởng chưa xác nhận kịp',
  HOLD_CANCELLED: 'Huỷ giữ chỗ',
  OTHER: 'Khác',
}

export const SOURCE_LABEL: Record<string, string> = {
  APP: 'qua ứng dụng',
  CHAT: 'qua trò chuyện',
  REMINDER_24H: 'qua lời nhắc 24h',
  BOARD: 'trên Board',
  QR_SCAN: 'quét QR',
  AUTO_CONFIRM: 'tự động',
  CONFIRM_DEADLINE: 'quá hạn xác nhận',
}

export const ACTOR_LABEL: Record<string, string> = {
  VEHICLE_OWNER: 'Khách',
  WORKSHOP_OWNER: 'Xưởng',
  SYSTEM: 'Hệ thống',
}
