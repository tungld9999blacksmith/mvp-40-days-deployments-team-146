import { describe, expect, it } from 'vitest'
import { historyCopilot } from './copilot'

const items = [
  { itemCode: 'BRAKE', itemName: 'Kiểm tra phanh', isCoveredByWarranty: false },
  { itemCode: 'CABIN_FILTER', itemName: 'Thay lọc gió điều hoà', isCoveredByWarranty: false },
  { itemCode: 'HV_BATTERY', itemName: 'Kiểm tra pin cao áp', isCoveredByWarranty: true },
]

function status(overrides: Record<string, unknown> = {}) {
  return {
    dueStatus: 'DUE_SOON',
    dueReason: 'KM',
    remainingKm: 1240,
    remainingDays: 23,
    nextMilestone: { odoMilestoneKm: 20000, monthMilestone: 24, dueDate: '2026-11-04', label: '', isRecurring: true, items },
    ...overrides,
  } as never
}

describe('historyCopilot', () => {
  it('names the due milestone with its real item and warranty counts', () => {
    const line = historyCopilot(status())
    expect(line).not.toBeNull()
    expect(`${line!.lead}${line!.figures}${line!.tail}`).toBe(
      'Mốc 20.000 km / 24 tháng (còn 1.240 km · 23 ngày) gồm 3 hạng mục, 1 được bảo hành. Xem chi phí dự kiến trước khi đặt lịch.',
    )
    expect(line!.action).toEqual({ to: '/estimate?odoMilestone=20000', label: 'Xem chi phí dự kiến' })
  })

  it('drops the warranty clause when nothing is covered', () => {
    const line = historyCopilot(status({ nextMilestone: { odoMilestoneKm: 20000, monthMilestone: 24, items: items.slice(0, 2) } }))
    expect(line!.figures).toBe('2 hạng mục')
  })

  it('stays silent when nothing is due, the status is unknown, or the items are not listed', () => {
    expect(historyCopilot(status({ dueStatus: 'NORMAL' }))).toBeNull()
    expect(historyCopilot(status({ dueStatus: 'UNKNOWN' }))).toBeNull()
    expect(historyCopilot(status({ nextMilestone: { odoMilestoneKm: 20000, monthMilestone: 24, items: [] } }))).toBeNull()
    expect(historyCopilot(null)).toBeNull()
  })
})
