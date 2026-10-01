/** FEAT-NOTI-001 — backend `modules/notification/schemas.py`, API-SPEC-NOTI-001 §C.5. */

export type NotificationChannel = 'DISCORD' | 'ZALO' | 'TELEGRAM' | 'SMS' | 'EMAIL' | (string & {})
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
