import { describe, expect, it } from 'vitest'
import type { WorkshopQuoteItem } from '@/features/quotes/types'
import type { BoardItem } from '@/features/workshop-board/types'
import { portalEntries, toFeedEntry } from './feed'
import type { NotificationItem } from './types'

const item = (overrides: Partial<NotificationItem>): NotificationItem => ({
  id: 'x:1',
  kind: 'MAINTENANCE_REMINDER',
  occurredAt: '2026-10-01T03:00:00Z',
  unread: false,
  reminder: null,
  quote: null,
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

  it('links quote results to the quote and shows the approved total', () => {
    const approved = toFeedEntry(
      item({ kind: 'QUOTE_RESULT', unread: true, quote: { quoteId: 'q1', status: 'APPROVED', approvedTotal: '1400000.00', workshopName: 'VinFast Smart City' } }),
    )
    expect(approved).toMatchObject({ tone: 'success', unread: true, action: { to: '/quotes/q1' } })
    expect(approved?.message).toContain('VinFast Smart City')
    expect(approved?.message).toMatch(/1\.400\.000/)
    const rejected = toFeedEntry(item({ kind: 'QUOTE_RESULT', quote: { quoteId: 'q2', status: 'REJECTED', approvedTotal: null, workshopName: null } }))
    expect(rejected?.tone).toBe('error')
  })

  it('links a 24h appointment reminder to the ticket and asks to act only while it is pending', () => {
    const bookingReminder = { bookingId: 'b1', bookingCode: 'EVC-SOON', bookingDate: '2026-10-08', timeSlot: '09:00:00', workshopName: 'VinFast Smart City' }
    const pending = toFeedEntry(item({ kind: 'BOOKING_REMINDER', unread: true, bookingReminder }))
    expect(pending).toMatchObject({ tone: 'warning', unread: true, action: { to: '/bookings/b1?src=REMINDER_24H' } })
    expect(pending?.message).toBe('EVC-SOON · 09:00 08/10/2026 tại VinFast Smart City. Xác nhận bạn sẽ đến, hoặc đổi / huỷ nếu cần.')
    const settled = toFeedEntry(item({ kind: 'BOOKING_REMINDER', bookingReminder: { ...bookingReminder, workshopName: null } }))
    expect(settled).toMatchObject({ tone: 'info', message: 'EVC-SOON · 09:00 08/10/2026.' })
    expect(toFeedEntry(item({ kind: 'BOOKING_REMINDER', bookingReminder: null }))).toBeNull()
  })

  it('skips an entry whose payload is missing instead of breaking the list', () => {
    expect(toFeedEntry(item({ kind: 'BOOKING_UPDATE', booking: null }))).toBeNull()
    expect(toFeedEntry(item({ kind: 'QUOTE_RESULT', quote: null }))).toBeNull()
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

  it('puts quotes waiting for review first, flagging the ones waiting over 24h', () => {
    const quote = {
      quoteId: 'q1', customer: { fullName: 'An', phone: '' }, modelName: 'VF 6', odoMilestone: 12_000,
      submittedAt: '2026-10-01T01:00:00Z', isWaitingLong: true,
    } as WorkshopQuoteItem
    const pending = { bookingId: 'b1', customer: { fullName: 'Bình', phone: '' }, vehicle: { modelName: 'VF 8', licensePlate: '' }, bookingDate: '2026-10-04', timeSlot: '09:00:00' } as BoardItem
    const entries = portalEntries([pending], [quote])
    expect(entries.map(entry => entry.id)).toEqual(['quote:q1', 'booking:b1'])
    expect(entries[0]).toMatchObject({ tone: 'warning', unread: true, action: { to: '/technician/quote-review?quoteId=q1' } })
  })
})

// Regression: smoke test 2026-10-10 — a decision the workshop recorded by phone never reached the feed
describe('phone decision entry', () => {
  it('tells the owner what was recorded and how to dispute it', () => {
    const entry = toFeedEntry(
      item({
        kind: 'BOOKING_LINE',
        unread: true,
        bookingLine: {
          bookingId: 'b1',
          bookingCode: 'EVC-1',
          lineId: 'l1',
          kind: 'EXTRA',
          status: 'APPROVED',
          itemName: 'Vệ sinh khoang máy',
          price: 100000,
          isSafetyCritical: false,
          workshopName: 'VinFast Thăng Long',
          decidedVia: 'PHONE',
          phoneConfirmedBy: 'Anh Trung',
        },
      }),
    )
    expect(entry?.title).toBe('Xưởng ghi nhận quyết định qua điện thoại')
    expect(entry?.message).toContain('rằng bạn đồng ý làm Vệ sinh khoang máy')
    expect(entry?.message).toContain('Tôi không đồng ý')
    expect(entry?.action?.to).toBe('/bookings/b1')
  })
})
