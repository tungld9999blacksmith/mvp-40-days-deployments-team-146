import type { NotificationSettings, NotificationSettingsUpdate, SettingsForm } from './types'

export function toForm(settings: NotificationSettings): SettingsForm {
  return {
    remindersEnabled: settings.remindersEnabled,
    reminderLeadDays: String(settings.reminderLeadDays),
    channels: Object.fromEntries(settings.channels.map(channel => [channel.channel, channel.enabled])),
  }
}

export function isDirty(saved: NotificationSettings, form: SettingsForm): boolean {
  return Object.keys(buildSettingsPatch(saved, form)).length > 0
}

/**
 * Body of PUT /notification-settings with only the changed fields (US-021 FE §7.2).
 * Never enables a channel that is not available (BR-506).
 */
export function buildSettingsPatch(saved: NotificationSettings, form: SettingsForm): NotificationSettingsUpdate {
  const patch: NotificationSettingsUpdate = {}
  if (form.remindersEnabled !== saved.remindersEnabled) patch.remindersEnabled = form.remindersEnabled
  const leadDays = Number(form.reminderLeadDays)
  if (form.reminderLeadDays.trim() !== '' && leadDays !== saved.reminderLeadDays) patch.reminderLeadDays = leadDays
  const channels = saved.channels
    .filter(channel => (form.channels[channel.channel] ?? channel.enabled) !== channel.enabled)
    .filter(channel => channel.available || !form.channels[channel.channel])
    .map(channel => ({ channel: channel.channel, enabled: form.channels[channel.channel] }))
  if (channels.length) patch.channels = channels
  return patch
}

export interface SettingsErrors {
  reminderLeadDays?: string
  channels?: string
}

/** Client validation (US-021 FE §8.1). */
export function validateSettings(form: SettingsForm): SettingsErrors {
  const errors: SettingsErrors = {}
  const raw = form.reminderLeadDays.trim()
  const value = Number(raw)
  if (raw === '' || !Number.isInteger(value)) errors.reminderLeadDays = 'Vui lòng nhập số ngày hợp lệ.'
  else if (value < 0 || value > 30) errors.reminderLeadDays = 'Số ngày nhắc trước phải từ 0 đến 30.'
  if (form.remindersEnabled && !Object.values(form.channels).some(Boolean)) {
    errors.channels = 'Chọn ít nhất một kênh nhận thông báo, hoặc tắt nhắc bảo dưỡng.'
  }
  return errors
}
