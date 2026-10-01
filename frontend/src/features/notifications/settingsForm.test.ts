import { describe, expect, it } from 'vitest'
import { buildSettingsPatch, isDirty, toForm, validateSettings } from './settingsForm'
import type { NotificationSettings } from './types'

const saved: NotificationSettings = {
  remindersEnabled: true,
  reminderLeadDays: 2,
  defaultReminderLeadDays: 2,
  channels: [
    { channel: 'DISCORD', enabled: true, available: true, status: 'NOT_CONNECTED' },
    { channel: 'SMS', enabled: false, available: false, status: 'COMING_SOON' },
  ],
}

describe('notification settings form (US-021 FE)', () => {
  it('sends only the changed fields (AC-FE-502)', () => {
    const form = { ...toForm(saved), reminderLeadDays: '5' }
    expect(buildSettingsPatch(saved, form)).toEqual({ reminderLeadDays: 5 })
    expect(isDirty(saved, form)).toBe(true)
    expect(isDirty(saved, toForm(saved))).toBe(false)
  })

  it('never enables a channel that is not available (BR-506)', () => {
    const form = { ...toForm(saved), channels: { DISCORD: true, SMS: true } }
    expect(buildSettingsPatch(saved, form)).toEqual({})
  })

  it('lead days must be an integer 0..30 (AC-FE-503)', () => {
    expect(validateSettings({ ...toForm(saved), reminderLeadDays: '31' }).reminderLeadDays).toBe('Số ngày nhắc trước phải từ 0 đến 30.')
    expect(validateSettings({ ...toForm(saved), reminderLeadDays: '0' }).reminderLeadDays).toBeUndefined()
  })

  it('reminders on require at least one channel (AC-FE-505)', () => {
    const form = { ...toForm(saved), channels: { DISCORD: false, SMS: false } }
    expect(validateSettings(form).channels).toBe('Chọn ít nhất một kênh nhận thông báo, hoặc tắt nhắc bảo dưỡng.')
    expect(validateSettings({ ...form, remindersEnabled: false }).channels).toBeUndefined()
  })
})
