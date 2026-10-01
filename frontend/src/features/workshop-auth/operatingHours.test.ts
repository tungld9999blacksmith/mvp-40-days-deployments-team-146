import { describe, expect, it } from 'vitest'
import { resolveWorkshopRoute } from './navigation'
import { defaultOperatingHours, normalizeOperatingHours, validateOperatingHours } from './operatingHours'

describe('operating hours (US-009 FE §4.3, BR-206)', () => {
  it('default week is Mon–Sat 08:00–17:30 and Sunday closed', () => {
    const hours = defaultOperatingHours()
    expect(hours).toHaveLength(7)
    expect(hours[0]).toEqual({ dayOfWeek: 1, isClosed: false, openTime: '08:00', closeTime: '17:30' })
    expect(hours[6]).toEqual({ dayOfWeek: 7, isClosed: true, openTime: null, closeTime: null })
  })

  it('always sends 7 rows ordered 1..7, closed days with null times', () => {
    const normalized = normalizeOperatingHours([{ dayOfWeek: 3, isClosed: false, openTime: '09:00', closeTime: '18:00' }])
    expect(normalized.map(hour => hour.dayOfWeek)).toEqual([1, 2, 3, 4, 5, 6, 7])
    expect(normalized[2].isClosed).toBe(false)
    expect(normalized[0]).toEqual({ dayOfWeek: 1, isClosed: true, openTime: null, closeTime: null })
  })

  it('close time must be after open time (EDGE-205), keyed like the backend field', () => {
    const hours = defaultOperatingHours()
    hours[5] = { dayOfWeek: 6, isClosed: false, openTime: '12:00', closeTime: '08:00' }
    expect(validateOperatingHours(hours)).toEqual({ 'operatingHours[5].closeTime': 'Giờ đóng cửa phải sau giờ mở cửa.' })
  })

  it('at least one open day', () => {
    const closed = defaultOperatingHours().map(hour => ({ ...hour, isClosed: true, openTime: null, closeTime: null }))
    expect(validateOperatingHours(closed).operatingHours).toBe('Xưởng phải mở cửa ít nhất 1 ngày trong tuần.')
  })
})

describe('resolveWorkshopRoute (US-009 FE §13.2)', () => {
  it('maps nextStep to portal routes', () => {
    expect(resolveWorkshopRoute({ nextStep: 'DASHBOARD', status: 'ACTIVE' })).toBe('/technician')
    expect(resolveWorkshopRoute({ nextStep: 'WORKSHOP', status: 'ONBOARDING_IN_PROGRESS' })).toBe('/workshop/onboarding/operations')
    expect(resolveWorkshopRoute({ nextStep: 'WORKSHOP', status: 'VERIFICATION_FAILED' })).toBe('/workshop/onboarding/failed')
  })
})
