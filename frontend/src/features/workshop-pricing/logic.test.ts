import { describe, expect, it } from 'vitest'
import { priceText, referenceText } from './logic'

// Regression: design review 2026-10-10 FINDING-002 — warranty checks read "0 ₫" on Bảng giá
describe('price list text', () => {
  it('reads 0 as free', () => {
    expect(priceText(0)).toBe('Miễn phí')
    expect(priceText(370_000)).toBe('370.000 ₫')
    expect(referenceText({ referencePrice: 0, referencePriceMin: 0 })).toBe('Miễn phí')
  })

  it('shows a range when the milestones differ', () => {
    expect(referenceText({ referencePrice: 350_000, referencePriceMin: 350_000 })).toBe('350.000 ₫')
    expect(referenceText({ referencePrice: 350_000, referencePriceMin: 200_000 })).toBe('200.000–350.000 ₫')
  })
})
