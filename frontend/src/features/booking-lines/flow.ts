import { useEffect, useState } from 'react'
import { apiGet } from '@/shared/api/client'
import type { PricingFlow } from './types'

/**
 * Pricing flow of NEW bookings (backend QUOTE_FLOW, bao-gia-hai-tang D7). Under `two_tier`
 * the price is set at booking time, so the apps hide "Gửi xưởng báo giá" and booking from an
 * approved quote (the backend refuses that with LEGACY_QUOTE_NOT_ACCEPTED). Fetched once per
 * page load; an error keeps the legacy behaviour.
 */
let pending: Promise<PricingFlow> | null = null

export function loadPricingFlow(): Promise<PricingFlow> {
  pending ??= apiGet<{ quoteFlow: PricingFlow }>('/pricing-flow', { timeoutMs: 8_000 })
    .then(data => (data.quoteFlow === 'two_tier' ? 'two_tier' : 'legacy') as PricingFlow)
    .catch(() => {
      pending = null // try again on the next screen
      return 'legacy' as PricingFlow
    })
  return pending
}

/** `null` while loading: callers render neither flow's actions until it is known. */
export function usePricingFlow(): PricingFlow | null {
  const [flow, setFlow] = useState<PricingFlow | null>(null)
  useEffect(() => {
    let alive = true
    void loadPricingFlow().then(value => alive && setFlow(value))
    return () => {
      alive = false
    }
  }, [])
  return flow
}

/** Under two_tier a booking never carries a legacy quote. */
export function legacyQuotesAllowed(flow: PricingFlow | null): boolean {
  return flow === 'legacy'
}
