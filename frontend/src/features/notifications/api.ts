import { apiGet, apiRequest } from '@/shared/api/client'
import type { DemoEmail, NotificationFeed, NotificationSettings, NotificationSettingsUpdate, ReminderContext } from './types'

export const NOTIFICATION_SETTINGS_KEY = 'notification-settings'
export const NOTIFICATION_FEED_KEY = 'notifications'

/** API-NOTI-001 — returns defaults when the owner never saved anything (AC-509). */
export function getNotificationSettings(): Promise<NotificationSettings> {
  return apiGet<NotificationSettings>('/notification-settings', { timeoutMs: 10_000 })
}

/** API-NOTI-002 — partial update: only the fields sent are changed. */
export async function updateNotificationSettings(body: NotificationSettingsUpdate): Promise<NotificationSettings> {
  return (await apiRequest<NotificationSettings>('/notification-settings', { method: 'PUT', body, timeoutMs: 10_000 })).data
}

/** API-NOTI-003 — reminders, quote results, booking updates and surveys of the last 90 days. */
export function listNotifications(): Promise<NotificationFeed> {
  return apiGet<NotificationFeed>('/notifications', { timeoutMs: 10_000 })
}

export function getReminderContext(id: string): Promise<ReminderContext> {
  return apiGet(`/notifications/reminders/${encodeURIComponent(id)}`, { timeoutMs: 10_000 })
}

export function getDemoEmailOutbox(): Promise<{ items: DemoEmail[]; mode: string; canRunReminders?: boolean; canSendTestEmail?: boolean }> {
  return apiGet('/notifications/email-outbox', { timeoutMs: 10_000 })
}

export async function runDemoReminders(): Promise<void> {
  await apiRequest('/demo/reminders/run', { method: 'POST', timeoutMs: 30_000 })
}

export async function sendDemoTestEmail(): Promise<void> {
  await apiRequest('/demo/email-test/send', { method: 'POST', body: {}, timeoutMs: 30_000 })
}
