import { describe, expect, it } from 'vitest'
import { tweenValue } from './useTween'

describe('tweenValue', () => {
  it('starts at from, ends at to, and eases out in between', () => {
    expect(tweenValue(18690, 18760, 0)).toBe(18690)
    expect(tweenValue(18690, 18760, 1)).toBe(18760)
    // Ease-out: past the linear midpoint at half time.
    expect(tweenValue(0, 1, 0.5)).toBeCloseTo(0.875, 3)
  })

  it('clamps progress outside 0–1', () => {
    expect(tweenValue(1, 0, -0.2)).toBe(1)
    expect(tweenValue(1, 0, 3)).toBe(0)
  })
})
