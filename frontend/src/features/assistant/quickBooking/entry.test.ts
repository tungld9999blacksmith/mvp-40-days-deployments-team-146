import { describe, expect, it } from 'vitest'
import { consumeQuickBookingIntent, QUICK_BOOKING_ENTRY_PATH } from './entry'

describe('quick-booking entry intent', () => {
  it('uses an explicit model-independent deep link', () => {
    expect(QUICK_BOOKING_ENTRY_PATH).toBe('/ai/new?intent=quick-booking')
  })

  it('consumes the intent while preserving other route context', () => {
    const remaining = consumeQuickBookingIntent(
      new URLSearchParams('intent=quick-booking&userVehicleId=vehicle-1'),
    )

    expect(remaining?.toString()).toBe('userVehicleId=vehicle-1')
  })

  it('ignores unrelated intents', () => {
    expect(consumeQuickBookingIntent(new URLSearchParams('intent=ask-ai'))).toBeNull()
  })
})
