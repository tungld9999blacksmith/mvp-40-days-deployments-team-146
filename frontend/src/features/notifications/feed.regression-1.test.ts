// Regression: in-app feed dropped two-tier price lines (BOOKING_LINE), so owners were never told about extras
// Found by /qa on 2026-10-10
// Report: .gstack/qa-reports/run-20261009T201844Z/qa-report-localhost-2026-10-10.md
import { describe, expect, it } from 'vitest'
import { toFeedEntry } from './feed'
import type { NotificationItem } from './types'

const line = (status: 'PROPOSED' | 'CONFIRMED', unread: boolean): NotificationItem =>
  ({
    id: `booking-line:l1:2`,
    kind: 'BOOKING_LINE',
    occurredAt: '2026-10-10T02:00:00Z',
    unread,
    reminder: null,
    booking: null,
    followUp: null,
    bookingLine: {
      bookingId: 'b1',
      bookingCode: 'EVC-FFAEE694',
      lineId: 'l1',
      kind: 'EXTRA',
      status,
      itemName: 'Thay má phanh trước',
      price: 1_500_000,
      isSafetyCritical: true,
      workshopName: 'VinFast Thăng Long',
    },
  }) as NotificationItem

describe('toFeedEntry — two-tier price lines', () => {
  it('asks the owner to decide on a proposed line and links to the ticket', () => {
    const entry = toFeedEntry(line('PROPOSED', true))
    expect(entry).toMatchObject({
      tone: 'warning',
      title: 'Cần bạn quyết định',
      unread: true,
      action: { label: 'Mở phiếu để quyết định', to: '/bookings/b1' },
    })
    expect(entry?.message).toMatch(/^VinFast Thăng Long đề xuất thêm Thay má phanh trước/)
    expect(entry?.message).toContain('Chỉ làm khi bạn đồng ý')
  })

  it('reports a reference price the workshop confirmed', () => {
    const entry = toFeedEntry(line('CONFIRMED', false))
    expect(entry).toMatchObject({ tone: 'info', title: 'Xưởng đã xác nhận giá', action: { to: '/bookings/b1' } })
    expect(entry?.message).toContain('1.500.000')
  })
})
