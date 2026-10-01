import { describe, expect, it } from 'vitest'
import { resolveOnboardingRoute } from './navigation'
import {
  isValidFullName,
  isValidHotline,
  isValidManufactureYear,
  isValidNationalId,
  isValidPhone,
  isValidPlate,
  isValidVin,
} from './validation'

describe('validation (US-001 / US-009 FE §8)', () => {
  it('phone: VN mobile with separators', () => {
    expect(isValidPhone('0901 000 001')).toBe(true)
    expect(isValidPhone('+84.901.000.001')).toBe(true)
    expect(isValidPhone('0123456789')).toBe(false)
  })

  it('VIN: 17 alphanumerics after uppercase (backend rule, accepts O as in manufacturer VINs)', () => {
    expect(isValidVin('rllvf6ab1ph000123')).toBe(true)
    expect(isValidVin('VF8ECO20230000001')).toBe(true)
    expect(isValidVin('RLLVF6AB1PH00012')).toBe(false)
    expect(isValidVin('RLLVF6AB1PH00012-')).toBe(false)
  })

  it('licence plate after removing separators', () => {
    expect(isValidPlate('30A-123.45')).toBe(true)
    expect(isValidPlate('30a12345')).toBe(true)
    expect(isValidPlate('ABC-123')).toBe(false)
  })

  it('national id: exactly 12 digits', () => {
    expect(isValidNationalId('0011 9000 0101')).toBe(true)
    expect(isValidNationalId('00119000010')).toBe(false)
  })

  it('hotline: mobile / landline / 1900-1800', () => {
    expect(isValidHotline('024 3765 4321')).toBe(true)
    expect(isValidHotline('1900 1234')).toBe(true)
    expect(isValidHotline('12345')).toBe(false)
  })

  it('full name: Vietnamese letters, 2–150 chars', () => {
    expect(isValidFullName('Nguyễn Văn A')).toBe(true)
    expect(isValidFullName('A')).toBe(false)
    expect(isValidFullName('Nguyen 123')).toBe(false)
  })

  it('manufacture year: 2015 … next year', () => {
    expect(isValidManufactureYear(2024)).toBe(true)
    expect(isValidManufactureYear(2014)).toBe(false)
  })
})

describe('resolveOnboardingRoute (US-001 FE §13.2)', () => {
  it('maps nextStep to routes', () => {
    expect(resolveOnboardingRoute({ nextStep: 'HOME', status: 'ACTIVE' })).toBe('/dashboard')
    expect(resolveOnboardingRoute({ nextStep: 'PROFILE', status: 'ONBOARDING_IN_PROGRESS' })).toBe('/onboarding/profile')
    expect(resolveOnboardingRoute({ nextStep: 'VERIFYING', status: 'PENDING_VEHICLE_VERIFICATION' })).toBe('/onboarding/verifying')
  })

  it('VEHICLE goes to the failure screen after a failed verification', () => {
    expect(resolveOnboardingRoute({ nextStep: 'VEHICLE', status: 'ONBOARDING_IN_PROGRESS' })).toBe('/onboarding/vehicle')
    expect(resolveOnboardingRoute({ nextStep: 'VEHICLE', status: 'VERIFICATION_FAILED' })).toBe('/onboarding/failed')
  })
})
