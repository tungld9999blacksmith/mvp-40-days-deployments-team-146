import { apiGet, apiRequest } from '@/shared/api/client'
import type { NotificationSettings, NotificationSettingsUpdate } from './types'

export const NOTIFICATION_SETTINGS_KEY = 'notification-settings'

/** API-NOTI-001 — returns defaults when the owner never saved anything (AC-509). */
export function getNotificationSettings(): Promise<NotificationSettings> {
  return apiGet<NotificationSettings>('/notification-settings', { timeoutMs: 10_000 })
}

/** API-NOTI-002 — partial update: only the fields sent are changed. */
export async function updateNotificationSettings(body: NotificationSettingsUpdate): Promise<NotificationSettings> {
  return (await apiRequest<NotificationSettings>('/notification-settings', { method: 'PUT', body, timeoutMs: 10_000 })).data
}
