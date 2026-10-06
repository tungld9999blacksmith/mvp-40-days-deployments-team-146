import { describe, expect, it } from 'vitest'
import { toBookingDetail, type TicketDto } from './ticketAdapter'

function ticket(overrides: Partial<TicketDto>): TicketDto {
  return {
    bookingId: 'b1',
    bookingCode: 'EVC-7K2M',
    status: 'CONFIRMED',
    bookingDate: '2026-10-04',
    timeSlot: '14:00',
    appointmentAt: '2026-10-04T07:00:00Z',
    history: [],
    ...overrides,
  } as TicketDto
}

describe('toBookingDetail', () => {
  it('maps backend history rows to the UI shape', () => {
    const detail = toBookingDetail(
      ticket({
        history: [
          {
            type: 'RESCHEDULE', at: '2026-10-02T03:00:00Z', actorType: 'VEHICLE_OWNER', source: 'APP',
            fromDate: '2026-10-03', fromTimeSlot: '09:00', toDate: '2026-10-04', toTimeSlot: '14:00',
          },
          {
            type: 'STATUS', at: '2026-10-01T03:00:00Z', actorType: 'SYSTEM', source: 'AUTO_CONFIRM',
            fromStatus: 'PENDING', toStatus: 'CONFIRMED', reasonCode: null,
          },
        ],
      }),
    )
    expect(detail.history).toEqual([
      {
        kind: 'RESCHEDULE', source: 'APP', at: '2026-10-02T03:00:00Z',
        from: { date: '2026-10-03', timeSlot: '09:00' }, to: { date: '2026-10-04', timeSlot: '14:00' },
      },
      {
        kind: 'STATUS', fromStatus: 'PENDING', toStatus: 'CONFIRMED', actorType: 'SYSTEM',
        source: 'AUTO_CONFIRM', reasonCode: null, note: null, at: '2026-10-01T03:00:00Z',
      },
    ])
  })

  it('derives the cancel summary from the newest transition to CANCELLED', () => {
    const detail = toBookingDetail(
      ticket({
        status: 'CANCELLED',
        history: [
          { type: 'STATUS', at: '2026-10-03T01:00:00Z', actorType: 'WORKSHOP_OWNER', source: 'BOARD', fromStatus: 'CONFIRMED', toStatus: 'CANCELLED', reasonCode: 'WORKSHOP_CLOSED' },
        ],
      }),
    )
    expect(detail.cancelledAt).toBe('2026-10-03T01:00:00Z')
    expect(detail.cancelledBy).toBe('WORKSHOP_OWNER')
    expect(detail.cancelReason).toBe('WORKSHOP_CLOSED')
    expect(detail.completedAt).toBeNull()
  })

  it('derives completedAt and leaves fields the backend does not send as null', () => {
    const detail = toBookingDetail(
      ticket({
        status: 'COMPLETED',
        history: [{ type: 'STATUS', at: '2026-10-04T09:00:00Z', actorType: 'WORKSHOP_OWNER', source: 'BOARD', fromStatus: 'IN_PROGRESS', toStatus: 'COMPLETED' }],
      }),
    )
    expect(detail.completedAt).toBe('2026-10-04T09:00:00Z')
    expect(detail.cancelledAt).toBeNull()
    expect(detail.followUp).toBeNull()
    expect(detail.ownerCancelableUntil).toBeNull()
  })

  it('keeps values the mock API already provides in the UI shape', () => {
    const detail = toBookingDetail(
      ticket({
        status: 'PENDING',
        ownerCancelableUntil: '2026-10-02T03:10:00Z',
        followUp: { followUpId: 'f1', canRespond: true },
        history: [{ kind: 'STATUS', fromStatus: null, toStatus: 'PENDING', actorType: 'VEHICLE_OWNER', source: 'APP', reasonCode: null, note: 'x', at: '2026-10-02T03:00:00Z' }],
      }),
    )
    expect(detail.ownerCancelableUntil).toBe('2026-10-02T03:10:00Z')
    expect(detail.followUp).toEqual({ followUpId: 'f1', canRespond: true })
    expect(detail.history[0]).toMatchObject({ kind: 'STATUS', note: 'x' })
  })
})
