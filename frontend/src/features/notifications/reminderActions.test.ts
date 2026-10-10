import { describe, expect, it } from 'vitest'
import { reminderActions, RESOLUTION_TEXT } from './reminderActions'
import type { ReminderContext } from './types'

const context = {
  reminderId: 'reminder-a', userVehicleId: 'second-vehicle', odoMilestoneKm: 24_000,
  resolved: true, resolutionReason: 'MAINTENANCE_COMPLETED',
  currentStatus: { nextMilestone: { odoMilestoneKm: 48_000 } },
} as ReminderContext

describe('actions from an email reminder', () => {
  it('keeps the correct vehicle and books the current milestone after maintenance', () => {
    const actions = reminderActions(context)
    const booking = new URL(actions.booking!, 'http://localhost')
    expect(booking.searchParams.get('userVehicleId')).toBe('second-vehicle')
    expect(booking.searchParams.get('odoMilestone')).toBe('48000')
    const chat = new URL(actions.chat, 'http://localhost')
    expect(chat.pathname).toBe('/ai/new')
    expect(chat.searchParams.get('userVehicleId')).toBe('second-vehicle')
    expect(chat.searchParams.get('q')).toContain('reminder-a')
  })

  it('offers no duplicate booking when the milestone already has an appointment', () => {
    expect(reminderActions({ ...context, hasCurrentBooking: true }).booking).toBeNull()
    expect(reminderActions({ ...context, resolutionReason: 'HAS_BOOKING', hasCurrentBooking: false }).booking).not.toBeNull()
  })

  it('does not invent a milestone when the current calculation has no schedule', () => {
    expect(reminderActions({ ...context, currentStatus: { ...context.currentStatus, nextMilestone: null } }).booking).toBeNull()
    expect(RESOLUTION_TEXT.MAINTENANCE_COMPLETED).toContain('hoàn tất')
    expect(RESOLUTION_TEXT.SUPERSEDED).toContain('quá hạn')
  })
})
