import { describe, expect, it } from 'vitest'
import { demoLoginErrorMessage, formatDemoResetIn } from './demoAccount'

const NOW = new Date('2026-10-11T03:00:00Z')

describe('formatDemoResetIn', () => {
  it('shows days and hours, hours, then minutes', () => {
    expect(formatDemoResetIn('2026-10-12T08:00:00Z', NOW)).toBe('1 ngày 5 giờ')
    expect(formatDemoResetIn('2026-10-13T03:00:00Z', NOW)).toBe('2 ngày')
    expect(formatDemoResetIn('2026-10-11T06:30:00Z', NOW)).toBe('3 giờ')
    expect(formatDemoResetIn('2026-10-11T03:44:10Z', NOW)).toBe('45 phút')
  })

  it('is null when unknown, invalid or already due', () => {
    expect(formatDemoResetIn(null, NOW)).toBeNull()
    expect(formatDemoResetIn('not a date', NOW)).toBeNull()
    expect(formatDemoResetIn('2026-10-11T02:00:00Z', NOW)).toBeNull()
  })
})

describe('demoLoginErrorMessage', () => {
  it('maps the backend codes', () => {
    expect(demoLoginErrorMessage('DEMO_RATE_LIMITED')).toContain('quá nhiều lần')
    expect(demoLoginErrorMessage('DEMO_ACCOUNT_UNAVAILABLE')).toContain('chưa sẵn sàng')
    expect(demoLoginErrorMessage('DEMO_LOGIN_DISABLED')).toContain('chưa sẵn sàng')
    expect(demoLoginErrorMessage('NETWORK_ERROR')).toContain('thử lại')
  })
})
