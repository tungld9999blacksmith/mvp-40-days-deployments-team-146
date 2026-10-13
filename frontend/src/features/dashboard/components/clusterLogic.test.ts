import { describe, expect, it } from 'vitest'
import { QUICK_BOOKING_ENTRY_PATH } from '@/features/assistant/quickBooking/entry'
import { daysGauge, gaugeTone, kmGauge, lastPeriodicService, monthlySpend, tellTales, voicePrompt } from './clusterLogic'

const NOW = new Date('2026-10-12T03:00:00Z')
const PERIODIC = { serviceDate: '2026-05-08', odoKm: 10000 }
const ODO = { odoKm: 18760, recordedAt: '2026-10-11T14:14:00Z', isStale: false, dataSource: 'OEM' }

function status(overrides: Record<string, unknown> = {}) {
  return {
    dueStatus: 'DUE_SOON',
    dueReason: 'KM',
    remainingKm: 1240,
    remainingDays: 23,
    nextMilestone: { odoMilestoneKm: 20000, monthMilestone: 24, dueDate: '2026-11-04', label: '', isRecurring: true, items: [] },
    odometer: ODO,

    ...overrides,
  } as never
}

describe('gaugeTone', () => {
  it('is amber on the axis that caused DUE_SOON and green on the other', () => {
    expect(gaugeTone(status(), 'km')).toBe('amber')
    expect(gaugeTone(status(), 'time')).toBe('green')
  })

  it('is red once that axis is past the milestone', () => {
    expect(gaugeTone(status({ dueStatus: 'OVERDUE', remainingKm: -320 }), 'km')).toBe('red')
  })

  it('is off when the status is unknown', () => {
    expect(gaugeTone(status({ dueStatus: 'UNKNOWN' }), 'km')).toBe('off')
    expect(gaugeTone(null, 'time')).toBe('off')
  })
})

describe('kmGauge', () => {
  it('draws from the last service km to the milestone, to scale', () => {
    const gauge = kmGauge(status(), PERIODIC)
    expect(gauge.fraction).toBeCloseTo(0.876, 3)
    expect(gauge.value).toBe('1.240')
    expect(gauge.unit).toBe('km tới mốc')
    expect(gauge.caption).toBe('Mốc 20.000 km')
    expect(gauge.ends).toEqual(['10.000', '20.000'])
  })

  it('fills the arc and reads "quá mốc" past the milestone', () => {
    const gauge = kmGauge(status({ dueStatus: 'OVERDUE', remainingKm: -320 }), PERIODIC)
    expect(gauge.fraction).toBe(1)
    expect(gauge.value).toBe('320')
    expect(gauge.unit).toBe('km quá mốc')
    expect(gauge.tone).toBe('red')
  })

  it('shows an empty track without a known milestone', () => {
    expect(kmGauge(status({ dueStatus: 'UNKNOWN' }))).toMatchObject({ fraction: null, value: null, caption: 'Chưa đủ dữ liệu' })
  })
})

describe('lastPeriodicService', () => {
  // Regression: the gauges started at status.lastService, which is any record, so a repair two days
  // ago made the days arc start on 10/10 instead of the periodic visit a year earlier.
  it('skips repairs and picks the newest periodic visit', () => {
    const records = [
      { serviceDate: '2026-10-10', odoKm: null, isPeriodic: false },
      { serviceDate: '2025-10-24', odoKm: 12040, isPeriodic: true },
      { serviceDate: '2024-10-22', odoKm: 6, isPeriodic: true },
    ]
    expect(lastPeriodicService(records)).toEqual(records[1])
    expect(lastPeriodicService(records.slice(0, 1))).toBeNull()
  })

  it('starts the km gauge at delivery (0 km) without a periodic visit', () => {
    const gauge = kmGauge(status(), null)
    expect(gauge.ends).toEqual(['0', '20.000'])
    expect(gauge.fraction).toBeCloseTo(18760 / 20000, 3)
  })
})

describe('daysGauge', () => {
  it('draws from the last service date to the due date', () => {
    const gauge = daysGauge(status(), PERIODIC, NOW)
    // 8 May → 4 Nov is 180 days; 157 of them have passed on 12 Oct.
    expect(gauge.fraction).toBeCloseTo(157 / 180, 3)
    expect(gauge.value).toBe('23')
    expect(gauge.caption).toBe('Hạn 04/11/2026')
    expect(gauge.ends).toEqual(['08/05/26', '04/11/26'])
  })

  it('keeps the figure but leaves the arc empty without a last service', () => {
    const gauge = daysGauge(status(), null, NOW)
    expect(gauge.fraction).toBeNull()
    expect(gauge.value).toBe('23')
    expect(gauge.ends).toBeNull()
  })
})

describe('tellTales', () => {
  const base = { status: status(), odometer: ODO, nextBooking: null, unseenQuotes: 0, quotesEnabled: true, warranties: null, now: NOW }

  it('lights only the states that need the owner', () => {
    const lamps = tellTales({ ...base, unseenQuotes: 2 })
    expect(lamps.map(lamp => [lamp.id, lamp.tone])).toEqual([
      ['maintenance', 'amber'],
      ['quotes', 'amber'],
      ['booking', 'off'],
      ['odo', 'off'],
    ])
    expect(lamps[1].label).toBe('2 báo giá có kết quả')
  })

  it('turns the maintenance lamp red when overdue and leaves out quotes when they are switched off', () => {
    const lamps = tellTales({ ...base, status: status({ dueStatus: 'OVERDUE' }), quotesEnabled: false })
    expect(lamps[0]).toMatchObject({ id: 'maintenance', tone: 'red' })
    expect(lamps.some(lamp => lamp.id === 'quotes')).toBe(false)
  })

  it('shows a confirmed booking green and a pending one amber, linking to the ticket', () => {
    const confirmed = tellTales({ ...base, nextBooking: { bookingId: 'B 1', status: 'CONFIRMED' } }).find(lamp => lamp.id === 'booking')
    expect(confirmed).toMatchObject({ tone: 'green', to: '/bookings/B%201?src=APP' })
    const pending = tellTales({ ...base, nextBooking: { bookingId: 'B1', status: 'PENDING' } }).find(lamp => lamp.id === 'booking')
    expect(pending?.tone).toBe('amber')
  })

  it('reads warranty from the backend isActive and the ending-soon window', () => {
    const active = { startDate: '2024-03-01', endDate: '2034-03-01', isActive: true }
    const ending = { startDate: '2024-03-01', endDate: '2027-01-01', isActive: true }
    expect(tellTales({ ...base, warranties: [active] }).find(lamp => lamp.id === 'warranty')?.tone).toBe('green')
    expect(tellTales({ ...base, warranties: [active, ending] }).find(lamp => lamp.id === 'warranty')?.tone).toBe('amber')
    expect(tellTales({ ...base, warranties: [{ ...active, isActive: false }] }).find(lamp => lamp.id === 'warranty')?.tone).toBe('off')
  })

  it('warns when the manufacturer ODO is stale', () => {
    const lamps = tellTales({ ...base, odometer: { ...ODO, isStale: true } })
    expect(lamps.find(lamp => lamp.id === 'odo')).toMatchObject({ tone: 'amber', label: 'ODO chưa được cập nhật' })
  })
})

describe('voicePrompt', () => {
  it('speaks first with the figures when the milestone is due and nothing is booked', () => {
    const prompt = voicePrompt({ status: status(), hasUpcomingBooking: false })
    expect(prompt).toMatchObject({ kind: 'proposal', actionLabel: 'Đặt lịch nhanh', to: QUICK_BOOKING_ENTRY_PATH })
    expect(prompt.kind === 'proposal' && prompt.text).toBe('Mốc 20.000 km / 24 tháng: còn 1.240 km · 23 ngày. Mình tìm xưởng và giờ trống gần bạn nhé?')
  })

  it('only suggests a question when a booking is open or nothing is due', () => {
    expect(voicePrompt({ status: status(), hasUpcomingBooking: true }).kind).toBe('question')
    expect(voicePrompt({ status: status({ dueStatus: 'NORMAL' }), hasUpcomingBooking: false }).kind).toBe('question')
  })
})

describe('monthlySpend', () => {
  it('sums recorded costs per month over the last 12 months', () => {
    const spend = monthlySpend(
      [
        { serviceDate: '2026-08-14', actualCost: 1420000 },
        { serviceDate: '2026-05-02', actualCost: '5000000' },
        { serviceDate: '2026-05-20', actualCost: null },
        { serviceDate: '2025-09-30', actualCost: 900000 },
      ],
      NOW,
    )
    expect(spend.months).toHaveLength(12)
    expect(spend.months[0]).toMatchObject({ key: '2025-11', label: '11' })
    expect(spend.months[11]).toMatchObject({ key: '2026-10', label: '10' })
    expect(spend.months.find(month => month.key === '2026-05')?.total).toBe(5000000)
    expect(spend.total).toBe(6420000)
    expect(spend.max).toBe(5000000)
  })
})
