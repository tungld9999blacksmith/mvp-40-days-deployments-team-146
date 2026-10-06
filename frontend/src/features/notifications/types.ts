/** FEAT-NOTI-001 — backend `modules/notification/schemas.py`, API-SPEC-NOTI-001 §C.5. */

export type NotificationChannel = 'ZALO' | 'TELEGRAM' | 'SMS' | 'EMAIL' | (string & {})
export type ChannelStatus = 'CONNECTED' | 'NOT_CONNECTED' | 'COMING_SOON' | (string & {})

export interface ChannelSetting {
  channel: NotificationChannel
  enabled: boolean
  available: boolean
  status: ChannelStatus
}

export interface NotificationSettings {
  remindersEnabled: boolean
  reminderLeadDays: number
  defaultReminderLeadDays: number
  channels: ChannelSetting[]
}

export interface NotificationSettingsUpdate {
  remindersEnabled?: boolean
  reminderLeadDays?: number
  channels?: { channel: NotificationChannel; enabled: boolean }[]
}

/** Editable part of the settings kept by the form. */
export interface SettingsForm {
  remindersEnabled: boolean
  reminderLeadDays: string
  channels: Record<string, boolean>
}

// ── API-NOTI-003 in-app feed (derived from existing records, no read state) ──
export type NotificationKind = 'MAINTENANCE_REMINDER' | 'BOOKING_UPDATE' | 'FOLLOW_UP'

export interface NotificationItem {
  id: string
  kind: NotificationKind
  occurredAt: string
  /** Only a survey waiting for an answer. */
  unread: boolean
  reminder: { userVehicleId: string; level: 'EARLY' | 'WARNING' | 'URGENT' | 'EXPIRED'; odoMilestoneKm: number; resolved: boolean } | null
  booking: {
    bookingId: string
    bookingCode: string
    status: 'CONFIRMED' | 'CANCELLED' | 'COMPLETED'
    reasonCode: string | null
    bookingDate: string
    timeSlot: string
    workshopName: string | null
  } | null
  followUp: { followUpId: string; bookingId: string; workshopName: string | null } | null
}

export interface NotificationFeed {
  items: NotificationItem[]
  unreadCount: number
}
