import type { ReminderContext } from './types'

export const RESOLUTION_TEXT: Record<string, string> = {
  HAS_BOOKING: 'Đã có lịch hẹn cho mốc này.',
  MAINTENANCE_COMPLETED: 'Đã hoàn tất bảo dưỡng; mốc tiếp theo được tính lại.',
  MILESTONE_CHANGED: 'Xe đã chuyển sang mốc bảo dưỡng khác.',
  SUPERSEDED: 'Lời nhắc sớm đã được thay bằng lời nhắc quá hạn.',
  BEFORE_WINDOW: 'Xe hiện chưa nằm trong khoảng nhắc đã cấu hình.',
  STATUS_CHANGED: 'Tình trạng xe đã thay đổi; lời nhắc này không còn áp dụng.',
}

export function reminderActions(context: ReminderContext) {
  const vehicle = { userVehicleId: context.userVehicleId }
  const current = context.currentStatus.nextMilestone
  const booked = context.hasCurrentBooking ?? (context.resolutionReason === 'HAS_BOOKING' && current?.odoMilestoneKm === context.odoMilestoneKm)
  return {
    booking: current && !booked
      ? `/booking?${new URLSearchParams({ ...vehicle, odoMilestone: String(current.odoMilestoneKm), ...(current.odoMilestoneKm === context.odoMilestoneKm ? { sourceReminderId: context.reminderId } : {}) })}`
      : null,
    chat: `/ai/new?${new URLSearchParams({ ...vehicle, q: `Hãy giải thích lời nhắc bảo dưỡng ${context.reminderId} và tình trạng hiện tại của xe tôi.` })}`,
  }
}
