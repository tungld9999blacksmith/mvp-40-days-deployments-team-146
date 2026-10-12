import type { NotificationSettings, NotificationSettingsUpdate, SettingsForm } from './types'

export function toForm(settings: NotificationSettings): SettingsForm {
  return {
    preferredSendTimeEnabled: Boolean(settings.preferredSendTime),
    preferredSendTime: settings.preferredSendTime ?? '19:00',
    quietHoursEnabled: Boolean(settings.quietHours),
    quietHoursStart: settings.quietHours?.start ?? '22:00',
    quietHoursEnd: settings.quietHours?.end ?? '07:00',
    timezone: settings.timezone ?? 'Asia/Ho_Chi_Minh',
    personalizedRemindersEnabled: settings.personalizedRemindersEnabled ?? false,
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
  if (saved.sendScheduleAvailable) {
    const preferred = form.preferredSendTimeEnabled ? form.preferredSendTime : null
    if (preferred !== (saved.preferredSendTime ?? null)) patch.preferredSendTime = preferred
    const quiet = form.quietHoursEnabled ? { start: form.quietHoursStart, end: form.quietHoursEnd } : null
    if (quiet?.start !== saved.quietHours?.start || quiet?.end !== saved.quietHours?.end) patch.quietHours = quiet
    if (form.timezone !== (saved.timezone ?? 'Asia/Ho_Chi_Minh')) patch.timezone = form.timezone
  }
  if (form.personalizedRemindersEnabled !== (saved.personalizedRemindersEnabled ?? false)) {
    patch.personalizedRemindersEnabled = form.personalizedRemindersEnabled
    if (form.personalizedRemindersEnabled) patch.personalizationPolicyVersion = saved.personalizationPolicyVersion
  }
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
  preferredSendTime?: string
  quietHours?: string
  timezone?: string
}

/** Client validation (US-021 FE §8.1). No channel is required: reminders always reach the in-app feed. */
export function validateSettings(form: SettingsForm): SettingsErrors {
  const errors: SettingsErrors = {}
  const raw = form.reminderLeadDays.trim()
  const value = Number(raw)
  if (raw === '' || !Number.isInteger(value)) errors.reminderLeadDays = 'Vui lòng nhập số ngày hợp lệ.'
  else if (value < 0 || value > 30) errors.reminderLeadDays = 'Số ngày nhắc trước phải từ 0 đến 30.'
  const validTime = (input: string) => /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(input)
  if (form.preferredSendTimeEnabled && !validTime(form.preferredSendTime)) errors.preferredSendTime = 'Chọn giờ nhận hợp lệ.'
  if (form.quietHoursEnabled && (!validTime(form.quietHoursStart) || !validTime(form.quietHoursEnd) || form.quietHoursStart === form.quietHoursEnd)) errors.quietHours = 'Chọn giờ bắt đầu và kết thúc khác nhau.'
  try { new Intl.DateTimeFormat('vi-VN', { timeZone: form.timezone }).format() }
  catch { errors.timezone = 'Chọn múi giờ hợp lệ.' }
  return errors
}
