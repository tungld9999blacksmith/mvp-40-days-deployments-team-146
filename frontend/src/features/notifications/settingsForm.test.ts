import { describe, expect, it } from 'vitest'
import { buildSettingsPatch, isDirty, toForm, validateSettings } from './settingsForm'
import type { NotificationSettings } from './types'

const saved: NotificationSettings = {
  remindersEnabled: true,
  reminderLeadDays: 2,
  defaultReminderLeadDays: 2,
  channels: [
    { channel: 'ZALO', enabled: false, available: false, status: 'COMING_SOON' },
    { channel: 'SMS', enabled: false, available: false, status: 'COMING_SOON' },
  ],
}

describe('notification settings form (US-021 FE)', () => {
  it('saves selected times without granting personalization or enabling a channel', () => {
    const settings = { ...saved, sendScheduleAvailable: true }
    const form = { ...toForm(settings), preferredSendTimeEnabled: true, preferredSendTime: '19:00', quietHoursEnabled: true }
    expect(buildSettingsPatch(settings, form)).toEqual({ preferredSendTime: '19:00', quietHours: { start: '22:00', end: '07:00' } })
    expect(validateSettings(form)).toEqual({})
  })
  it('clears selected times explicitly and preserves omitted preferences', () => {
    const settings = { ...saved, sendScheduleAvailable: true, preferredSendTime: '19:00', quietHours: { start: '22:00', end: '07:00' } }
    expect(isDirty(settings, toForm(settings))).toBe(false)
    expect(buildSettingsPatch(settings, { ...toForm(settings), preferredSendTimeEnabled: false, quietHoursEnabled: false })).toEqual({ preferredSendTime: null, quietHours: null })
    expect(buildSettingsPatch(settings, { ...toForm(settings), timezone: 'Asia/Tokyo' })).toEqual({ timezone: 'Asia/Tokyo' })
  })
  it('rejects malformed times, all-day silence and unknown timezone', () => {
    const form = { ...toForm(saved), preferredSendTimeEnabled: true, preferredSendTime: '25:00', quietHoursEnabled: true, quietHoursStart: '07:00', quietHoursEnd: '07:00', timezone: 'Mars/Zone' }
    expect(Object.keys(validateSettings(form)).sort()).toEqual(['preferredSendTime', 'quietHours', 'timezone'])
  })
  it('does not send scheduling fields to a backend without P2 support', () => {
    expect(buildSettingsPatch(saved, { ...toForm(saved), preferredSendTimeEnabled: true, quietHoursEnabled: true })).toEqual({})
  })
  it('requires the current policy version when opting in, and preserves channel choices', () => {
    const settings = { ...saved, personalizationPolicyVersion: 'driving-usage-2026-10-v1' }
    const form = { ...toForm(settings), personalizedRemindersEnabled: true }
    expect(buildSettingsPatch(settings, form)).toEqual({ personalizedRemindersEnabled: true, personalizationPolicyVersion: 'driving-usage-2026-10-v1' })
    const enabled = { ...settings, personalizedRemindersEnabled: true }
    expect(buildSettingsPatch(enabled, { ...toForm(enabled), remindersEnabled: false })).toEqual({ remindersEnabled: false })
    expect(buildSettingsPatch(enabled, { ...toForm(enabled), personalizedRemindersEnabled: false })).toEqual({ personalizedRemindersEnabled: false })
  })
  it('sends only the changed fields (AC-FE-502)', () => {
    const form = { ...toForm(saved), reminderLeadDays: '5' }
    expect(buildSettingsPatch(saved, form)).toEqual({ reminderLeadDays: 5 })
    expect(isDirty(saved, form)).toBe(true)
    expect(isDirty(saved, toForm(saved))).toBe(false)
  })

  it('never enables a channel that is not available (BR-506)', () => {
    const form = { ...toForm(saved), channels: { ZALO: true, SMS: true } }
    expect(buildSettingsPatch(saved, form)).toEqual({})
  })

  it('lead days must be an integer 0..30 (AC-FE-503)', () => {
    expect(validateSettings({ ...toForm(saved), reminderLeadDays: '31' }).reminderLeadDays).toBe('Số ngày nhắc trước phải từ 0 đến 30.')
    expect(validateSettings({ ...toForm(saved), reminderLeadDays: '0' }).reminderLeadDays).toBeUndefined()
  })

  it('reminders can stay on without any external channel (in-app feed only)', () => {
    const form = { ...toForm(saved), channels: { ZALO: false, SMS: false } }
    expect(validateSettings(form)).toEqual({})
  })
})
