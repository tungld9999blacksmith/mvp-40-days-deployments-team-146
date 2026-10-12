import { describe, expect, it } from 'vitest'
import type { VehicleSummary } from '../types'
import { isBookingInProgress, resolveCurrentVehicle, returnPathAfterSwitch, selectVehiclePath } from './resolve'

function vehicle(id: string): VehicleSummary {
  return { userVehicleId: id, modelName: 'VF 6', trim: 'Plus', licensePlate: `30A${id}`, color: null }
}

const ONE = [vehicle('v1')]
const THREE = [vehicle('v1'), vehicle('v2'), vehicle('v3')]

describe('resolveCurrentVehicle', () => {
  it('uses the vehicle named by the link over the remembered one', () => {
    expect(resolveCurrentVehicle({ vehicles: THREE, requestedId: 'v3', rememberedId: 'v2' })).toEqual({
      kind: 'selected',
      vehicle: THREE[2],
      source: 'query',
    })
  })

  it('reports a link to a vehicle the owner does not have', () => {
    expect(resolveCurrentVehicle({ vehicles: THREE, requestedId: 'other', rememberedId: 'v2' })).toEqual({ kind: 'not-found' })
  })

  it('uses the remembered vehicle', () => {
    expect(resolveCurrentVehicle({ vehicles: THREE, requestedId: null, rememberedId: 'v2' })).toEqual({
      kind: 'selected',
      vehicle: THREE[1],
      source: 'remembered',
    })
  })

  it('asks again when the remembered vehicle was unlinked', () => {
    expect(resolveCurrentVehicle({ vehicles: THREE, requestedId: null, rememberedId: 'gone' })).toEqual({ kind: 'needs-selection' })
  })

  it('picks the only vehicle without asking, even when another one was remembered', () => {
    expect(resolveCurrentVehicle({ vehicles: ONE, requestedId: null, rememberedId: 'gone' })).toEqual({
      kind: 'selected',
      vehicle: ONE[0],
      source: 'only',
    })
  })

  it('has no vehicle to show for an owner without vehicles, even with a link', () => {
    expect(resolveCurrentVehicle({ vehicles: [], requestedId: 'v1', rememberedId: null })).toEqual({ kind: 'none' })
  })

  it('asks an owner with several vehicles and nothing remembered', () => {
    expect(resolveCurrentVehicle({ vehicles: THREE, requestedId: null, rememberedId: null })).toEqual({ kind: 'needs-selection' })
  })
})

describe('returnPathAfterSwitch', () => {
  it.each([
    [null, '/dashboard'],
    ['//evil.com', '/dashboard'],
    ['https://evil.com', '/dashboard'],
    ['/\\evil.com', '/dashboard'],
    ['/select-vehicle?returnTo=%2Fhistory', '/dashboard'],
  ])('falls back to the dashboard for %s', (returnTo, expected) => {
    expect(returnPathAfterSwitch(returnTo)).toBe(expected)
  })

  it.each([
    ['/booking/slots?workshopId=1&date=2026-10-12', '/booking'],
    ['/booking?userVehicleId=v1&odoMilestone=24000', '/booking'],
    ['/ai/conv-1', '/ai'],
    ['/estimate/compare?odoMilestone=24000', '/estimate'],
    ['/quotes/q-1', '/dashboard'],
    ['/quotes/new?userVehicleId=v1', '/dashboard'],
    ['/bookings/b-1/reschedule', '/dashboard'],
    ['/follow-ups/f-1', '/dashboard'],
    ['/notifications/reminders/r-1', '/dashboard'],
  ])('leaves screens tied to the old vehicle: %s', (returnTo, expected) => {
    expect(returnPathAfterSwitch(returnTo)).toBe(expected)
  })

  it('keeps vehicle screens but drops the old userVehicleId', () => {
    expect(returnPathAfterSwitch('/history?userVehicleId=v1&tab=oem')).toBe('/history?tab=oem')
    expect(returnPathAfterSwitch('/vehicle')).toBe('/vehicle')
    expect(returnPathAfterSwitch('/bookings')).toBe('/bookings')
  })
})

describe('selectVehiclePath', () => {
  it('encodes the path to come back to', () => {
    expect(selectVehiclePath('/history?tab=oem')).toBe('/select-vehicle?returnTo=%2Fhistory%3Ftab%3Doem')
  })
})

describe('isBookingInProgress', () => {
  it.each([
    ['/booking', '', false],
    ['/booking', '?workshopId=1', true],
    ['/booking/slots', '?date=2026-10-12', true],
    ['/bookings', '', false],
    ['/bookings/b-1', '', false],
  ])('%s%s → %s', (pathname, search, expected) => {
    expect(isBookingInProgress(pathname, search)).toBe(expected)
  })
})
