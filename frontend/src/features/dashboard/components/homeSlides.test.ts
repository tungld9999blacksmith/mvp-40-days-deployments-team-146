import { describe, expect, it } from 'vitest'
import { wrapIndex } from '@/shared/ui/Carousel'
import { homeSlideKinds } from './homeSlides'

const milestone = { odoMilestoneKm: 24000, monthMilestone: 24 } as never

describe('homeSlideKinds', () => {
  it('shows maintenance, booking and assistant when the milestone is known and nothing is booked', () => {
    expect(homeSlideKinds({ status: { dueStatus: 'DUE_SOON', nextMilestone: milestone }, hasUpcomingBooking: false })).toEqual([
      'maintenance',
      'booking',
      'assistant',
    ])
  })

  it('drops the booking slide when an appointment is already upcoming', () => {
    expect(homeSlideKinds({ status: { dueStatus: 'NORMAL', nextMilestone: milestone }, hasUpcomingBooking: true })).toEqual([
      'maintenance',
      'assistant',
    ])
  })

  it('drops the maintenance slide while the status is unknown or still loading', () => {
    expect(homeSlideKinds({ status: { dueStatus: 'UNKNOWN', nextMilestone: null }, hasUpcomingBooking: false })).toEqual([
      'booking',
      'assistant',
    ])
    expect(homeSlideKinds({ status: null, hasUpcomingBooking: true })).toEqual(['assistant'])
  })
})

describe('wrapIndex', () => {
  it('wraps forward and backward', () => {
    expect(wrapIndex(3, 3)).toBe(0)
    expect(wrapIndex(-1, 3)).toBe(2)
    expect(wrapIndex(1, 3)).toBe(1)
    expect(wrapIndex(5, 0)).toBe(0)
  })
})
