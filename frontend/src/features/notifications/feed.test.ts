import { describe, expect, it } from 'vitest'
import type { BoardItem } from '@/features/workshop-board/types'
import { portalEntries, toFeedEntry } from './feed'
import type { NotificationItem } from './types'

const item = (overrides: Partial<NotificationItem>): NotificationItem => ({
  id: 'x:1',
  kind: 'MAINTENANCE_REMINDER',
  occurredAt: '2026-10-01T03:00:00Z',
  unread: false,
  reminder: null,
  booking: null,
  followUp: null,
  ...overrides,
})

describe('toFeedEntry', () => {
  it('turns an open reminder into a booking prompt and a resolved one into a note', () => {
    const open = toFeedEntry(item({ reminder: { userVehicleId: 'v1', level: 'EXPIRED', odoMilestoneKm: 12_000, resolved: false } }))
    expect(open).toMatchObject({ tone: 'warning', title: 'Đã quá hạn bảo dưỡng', action: { to: '/booking' } })
    const resolved = toFeedEntry(item({ reminder: { userVehicleId: 'v1', level: 'WARNING', odoMilestoneKm: 12_000, resolved: true } }))
    expect(resolved?.action).toBeNull()
    expect(resolved?.message).toContain('đã có lịch hẹn')
  })

  it('describes workshop booking updates with code, slot and link', () => {
    const entry = toFeedEntry(
      item({
        kind: 'BOOKING_UPDATE',
        booking: { bookingId: 'b1', bookingCode: 'EVC-7K2M', status: 'CANCELLED', reasonCode: 'WORKSHOP_CLOSED', bookingDate: '2026-10-04', timeSlot: '14:00:00', workshopName: null },
      }),
    )
    expect(entry).toMatchObject({ tone: 'error', title: 'Lịch hẹn đã bị huỷ', action: { to: '/bookings/b1' } })
    expect(entry?.message).toContain('EVC-7K2M · 14:00 04/10/2026')
  })

  it('links a pending survey to the follow-up form', () => {
    const entry = toFeedEntry(item({ kind: 'FOLLOW_UP', unread: true, followUp: { followUpId: 'f1', bookingId: 'b1', workshopName: 'X' } }))
    expect(entry?.action?.to).toBe('/follow-ups/f1')
  })

  it('skips an entry whose payload is missing instead of breaking the list', () => {
    expect(toFeedEntry(item({ kind: 'BOOKING_UPDATE', booking: null }))).toBeNull()
  })
})

describe('portalEntries', () => {
  it('lists bookings waiting for confirmation with a link to the board', () => {
    const pending = {
      bookingId: 'b1', customer: { fullName: 'An', phone: '' }, vehicle: { modelName: 'VF 6', licensePlate: '30A12345' },
      bookingDate: '2026-10-04', timeSlot: '09:00:00',
    } as BoardItem
    const [entry] = portalEntries([pending])
    expect(entry).toMatchObject({ id: 'booking:b1', tone: 'warning', unread: true, action: { to: '/technician/board/b1' } })
    expect(entry.message).toBe('An · VF 6 · 09:00 04/10/2026')
  })
})
