import { describe, expect, it } from 'vitest'
import type { BookingProposalCard, MessageDto } from '../types'
import { patchProposalCard, proposalView, QUICK_BOOKING_LABEL } from './proposalView'

const NOW = new Date('2026-10-03T03:00:00Z')

function card(overrides: Partial<BookingProposalCard> = {}): BookingProposalCard {
  return {
    type: 'BOOKING_PROPOSAL',
    version: 1,
    proposalId: 'p-1',
    vehicle: { userVehicleId: 'v-1', modelName: 'VF6', trim: 'Plus', licensePlateMasked: '30A***45' },
    milestone: null,
    reason: 'Xe đã quá mốc 12.000 km.',
    locationBasis: 'DEVICE',
    locationLabel: null,
    primary: {
      optionId: 'opt-1',
      workshopId: 'w-1',
      workshopName: 'VinFast Thanh Xuân',
      address: '68 Lê Văn Lương',
      region: 'Hà Nội',
      distanceKm: 1.84,
      isPreferred: false,
      date: '2026-10-05',
      timeSlot: '10:00',
      estimate: null,
    },
    alternatives: [],
    expiresAt: '2026-10-03T03:30:00Z',
    status: 'PROPOSED',
    booking: null,
    ...overrides,
  }
}

const booking = (status: string, bookingCode: string | null) => ({
  bookingId: 'b-1',
  bookingCode,
  status,
  ownerCancelableUntil: null,
})

describe('proposalView', () => {
  it('keeps the exact chip label', () => {
    expect(QUICK_BOOKING_LABEL).toBe('Đặt lịch bảo dưỡng nhanh')
  })

  it('offers the three actions only while PROPOSED', () => {
    expect(proposalView(card(), NOW).actions).toEqual(['confirm', 'revise', 'cancel'])
    for (const status of ['CANCELLED', 'SUPERSEDED', 'EXPIRED'] as const) {
      expect(proposalView(card({ status }), NOW).actions).toEqual([])
    }
    expect(proposalView(card({ status: 'CONFIRMED', booking: booking('CONFIRMED', 'EVC-1') }), NOW).actions).toEqual([])
  })

  it('reads a PROPOSED card past expiresAt as EXPIRED and offers a new proposal', () => {
    const view = proposalView(card(), new Date('2026-10-03T03:31:00Z'))
    expect(view.status).toBe('EXPIRED')
    expect(view.actions).toEqual([])
    expect(view.canRetry).toBe(true)
  })

  it('shows the code only for a confirmed booking, never while PENDING (AC-1509)', () => {
    const confirmed = proposalView(card({ status: 'CONFIRMED', booking: booking('CONFIRMED', 'EVC-3289E0B2') }), NOW)
    expect(confirmed.code).toBe('EVC-3289E0B2')
    expect(confirmed.badge.label).toBe('Đã xác nhận')
    expect(confirmed.ticketHref).toBe('/bookings/b-1')

    const pending = proposalView(card({ status: 'CONFIRMED', booking: booking('PENDING', null) }), NOW)
    expect(pending.code).toBeNull()
    expect(pending.badge.label).toBe('Chờ xưởng xác nhận')
    expect(pending.note).toContain('mã đặt lịch có sau khi xưởng xác nhận')
  })

  it('shows a distance only when the backend computed one (AC-1505)', () => {
    expect(proposalView(card(), NOW).distanceText).toBe('1,8 km')
    const byArea = card({
      locationBasis: 'PROVINCE',
      locationLabel: 'Xưởng trong khu vực Hà Nội',
      primary: { ...card().primary, distanceKm: null },
    })
    const view = proposalView(byArea, NOW)
    expect(view.distanceText).toBeNull()
    expect(view.areaText).toBe('Xưởng trong khu vực Hà Nội')
  })
})

describe('patchProposalCard', () => {
  const message = (id: string, proposalId: string | null): MessageDto => ({
    id,
    seq: 1,
    role: 'assistant',
    content: '',
    citations: [],
    refs: {},
    card: proposalId ? { ...(card({ proposalId }) as unknown as Record<string, unknown>), type: 'BOOKING_PROPOSAL' } : null,
    createdAt: '2026-10-03T03:00:00Z',
  })

  it('returns only the messages of that proposal, with the patch applied', () => {
    const patched = patchProposalCard([message('m1', 'p-1'), message('m2', 'p-2'), message('m3', null)], 'p-1', {
      status: 'CONFIRMED',
      booking: booking('CONFIRMED', 'EVC-1'),
    })
    expect(patched.map(m => m.id)).toEqual(['m1'])
    expect(patched[0].card?.status).toBe('CONFIRMED')
    expect((patched[0].card?.booking as { bookingCode: string }).bookingCode).toBe('EVC-1')
  })
})
