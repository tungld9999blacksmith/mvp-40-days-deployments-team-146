import { describe, expect, it } from 'vitest'
import { appointmentIso, BOOKING_CODE_PATTERN, codeFromQr } from './utils'

describe('codeFromQr', () => {
  it('reads the code from the ticket URL or the bare code', () => {
    expect(codeFromQr('https://evcare.vn/c/EVC-7F3A9C21')).toBe('EVC-7F3A9C21')
    expect(codeFromQr('http://localhost:5173/c/evc-7f3a9c21/')).toBe('EVC-7F3A9C21')
    expect(codeFromQr('  evc-1234abcd ')).toBe('EVC-1234ABCD')
  })

  it('accepts only 4–20 letters, digits or dashes', () => {
    expect(BOOKING_CODE_PATTERN.test('EVC-7F3A9C21')).toBe(true)
    expect(BOOKING_CODE_PATTERN.test('EV')).toBe(false)
    expect(BOOKING_CODE_PATTERN.test('EVC 7F3A')).toBe(false)
  })
})

describe('appointmentIso', () => {
  it('treats the booking day and slot as Vietnam time', () => {
    expect(appointmentIso('2026-10-04', '09:00:00')).toBe('2026-10-04T02:00:00.000Z')
    expect(appointmentIso('2026-10-04', '00:30')).toBe('2026-10-03T17:30:00.000Z')
  })
})
