// Regression: ISSUE-001 — typed digits appended to the prefilled price were silently cut to 9 digits
// Found by /qa on 2026-10-10
// Report: .gstack/qa-reports/run-20261009T201844Z/qa-report-localhost-2026-10-10.md
import { describe, expect, it } from 'vitest'
import { nextMoneyDigits } from './MoneyInput'

describe('nextMoneyDigits', () => {
  it('rejects an edit that would exceed 9 digits instead of truncating it', () => {
    // Prefill 200000, the caret lands at the end, the user types 180000.
    expect(nextMoneyDigits('200000', '200000180000')).toBe('200000')
  })

  it('keeps ordinary edits and strips separators', () => {
    expect(nextMoneyDigits('', '180.000')).toBe('180000')
    expect(nextMoneyDigits('180000', '')).toBe('')
    expect(nextMoneyDigits('', '999999999')).toBe('999999999')
  })
})
