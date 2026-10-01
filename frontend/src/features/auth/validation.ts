/** Client-side validation shared by owner and workshop onboarding (FE specs §8). */

const PHONE_RE = /^(0|\+84)(3|5|7|8|9)[0-9]{8}$/
// TODO(spec): US-001 FE §8 excludes I, O, Q (`^[A-HJ-NPR-Z0-9]{17}$`), but the backend accepts any
// 17 alphanumerics and the manufacturer mock seeds VINs such as VF8ECO20230000001. Following the
// backend so valid manufacturer VINs are not blocked.
const VIN_RE = /^[A-Z0-9]{17}$/
const PLATE_RE = /^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$/
const NATIONAL_ID_RE = /^[0-9]{12}$/
const HOTLINE_RE = /^((\+84|0)[0-9]{9,10}|(1900|1800)[0-9]{4,6})$/
const NAME_RE = /^[\p{L}\s'.-]+$/u

export function stripSeparators(value: string): string {
  return value.replace(/[\s.-]/g, '')
}

export function normalizeVin(value: string): string {
  return value.trim().toUpperCase()
}

export function normalizePlate(value: string): string {
  return stripSeparators(value.toUpperCase())
}

export function normalizeNationalId(value: string): string {
  return value.replace(/\s/g, '')
}

export function isValidPhone(value: string): boolean {
  return PHONE_RE.test(stripSeparators(value))
}

export function isValidVin(value: string): boolean {
  return VIN_RE.test(normalizeVin(value))
}

export function isValidPlate(value: string): boolean {
  return PLATE_RE.test(normalizePlate(value))
}

export function isValidNationalId(value: string): boolean {
  return NATIONAL_ID_RE.test(normalizeNationalId(value))
}

export function isValidHotline(value: string): boolean {
  return HOTLINE_RE.test(stripSeparators(value))
}

export function isValidFullName(value: string): boolean {
  const name = value.trim().replace(/\s+/g, ' ')
  return name.length >= 2 && name.length <= 150 && NAME_RE.test(name)
}

/** Past date, not before 1900-01-01. `value` is `YYYY-MM-DD`. */
export function isValidBirthDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return value >= '1900-01-01' && date < today
}

export function isValidManufactureYear(value: number): boolean {
  const max = new Date().getFullYear() + 1
  return Number.isInteger(value) && value >= 2015 && value <= max
}
