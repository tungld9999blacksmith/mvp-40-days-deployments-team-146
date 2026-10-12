import { describe, expect, it } from 'vitest'
import { orderByUrgency } from './urgency'

const ids = (items: { userVehicleId: string }[]) => items.map(item => item.userVehicleId)

describe('orderByUrgency', () => {
  const vehicles = ['a', 'b', 'c', 'd', 'e'].map(userVehicleId => ({ userVehicleId }))

  it('puts overdue first, then due soon, then normal (FINDING-010)', () => {
    const statuses = { a: 'NORMAL', b: 'DUE_SOON', c: 'OVERDUE', d: 'NORMAL', e: 'OVERDUE' } as const
    expect(ids(orderByUrgency(vehicles, statuses))).toEqual(['c', 'e', 'b', 'a', 'd'])
  })

  it('keeps link order inside a group and sends unknown or failed statuses last', () => {
    const statuses = { a: 'UNKNOWN', b: null, c: 'NORMAL', e: 'DUE_SOON' } as const
    expect(ids(orderByUrgency(vehicles, statuses))).toEqual(['e', 'c', 'a', 'b', 'd'])
  })

  it('does not change the input', () => {
    const copy = [...vehicles]
    orderByUrgency(vehicles, { e: 'OVERDUE' })
    expect(vehicles).toEqual(copy)
  })
})
