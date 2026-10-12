import { describe, expect, it } from 'vitest'
import { tripBookingLink, validateTrip } from './tripPlanning'
import type { TripPlan } from './types'

describe('trip planning', () => {
  it('rejects reversed dates and invalid distance', () => {
    expect(validateTrip('2026-10-20', '2026-10-19', '1200')).toBeTruthy()
    expect(validateTrip('2026-10-20', '', '0')).toBeTruthy()
    expect(validateTrip('2026-10-20', '', '20001')).toBeTruthy()
    expect(validateTrip('2026-10-20', '', '2.5')).toBeTruthy()
    expect(validateTrip('2026-10-20', '', '1200')).toBeNull()
  })
  it('passes owner vehicle and consented suggestions to booking without a time slot', () => {
    const plan = { advice: { milestoneKm: 12000, preferredWorkshop: { workshop_id: 'workshop' }, preferredServiceWindow: { suggestedDate: '2026-10-18' } } } as TripPlan
    const url = new URL(tripBookingLink('vehicle', plan), 'http://local')
    expect(url.searchParams.get('userVehicleId')).toBe('vehicle')
    expect(url.searchParams.get('workshopId')).toBe('workshop')
    expect(url.searchParams.get('date')).toBe('2026-10-18')
    expect(url.searchParams.has('timeSlot')).toBe(false)
    expect(url.searchParams.has('sourceReminderId')).toBe(false)
  })
})
