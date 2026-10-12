import type { VehicleSummary } from '../types'

export type CurrentVehicleResolution =
  | { kind: 'selected'; vehicle: VehicleSummary; source: 'query' | 'remembered' | 'only' }
  /** Two or more vehicles and nothing valid to pick from: the owner chooses on /select-vehicle. */
  | { kind: 'needs-selection' }
  /** No linked vehicle, even when a link asks for one: the existing "Bạn chưa có xe" state. */
  | { kind: 'none' }
  /** A link names a vehicle the owner does not have: the existing "Không tìm thấy xe" state. */
  | { kind: 'not-found' }

/** Picks the vehicle the owner screens show: link (`?userVehicleId=`) > remembered > the only one > ask. */
export function resolveCurrentVehicle({
  vehicles,
  requestedId,
  rememberedId,
}: {
  vehicles: VehicleSummary[]
  requestedId: string | null
  rememberedId: string | null
}): CurrentVehicleResolution {
  if (vehicles.length === 0) return { kind: 'none' }
  if (requestedId) {
    const requested = vehicles.find(vehicle => vehicle.userVehicleId === requestedId)
    return requested ? { kind: 'selected', vehicle: requested, source: 'query' } : { kind: 'not-found' }
  }
  const remembered = rememberedId ? vehicles.find(vehicle => vehicle.userVehicleId === rememberedId) : undefined
  if (remembered) return { kind: 'selected', vehicle: remembered, source: 'remembered' }
  if (vehicles.length === 1) return { kind: 'selected', vehicle: vehicles[0], source: 'only' }
  return { kind: 'needs-selection' }
}

export const SELECT_VEHICLE_PATH = '/select-vehicle'

/** Where the vehicle picker sends the owner back to; `returnTo` is the path + search they came from. */
export function selectVehiclePath(returnTo: string): string {
  return `${SELECT_VEHICLE_PATH}?returnTo=${encodeURIComponent(returnTo)}`
}

/** Screens tied to one record (a quote, a booking...) do not make sense for another vehicle. */
const RECORD_ROUTES = [/^\/quotes\/[^/]+/, /^\/bookings\/.+/, /^\/follow-ups\/[^/]+/, /^\/notifications\/reminders\/[^/]+/]

/**
 * Path to open after picking a vehicle. Only same-app paths are followed, and `userVehicleId` is
 * dropped from the query so an old link cannot override the vehicle just picked.
 */
export function returnPathAfterSwitch(returnTo: string | null): string {
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//') || returnTo.includes('\\')) return '/dashboard'
  const url = new URL(returnTo, 'http://app.local')
  const path = url.pathname
  if (path === SELECT_VEHICLE_PATH) return '/dashboard'
  if (path === '/booking' || path.startsWith('/booking/')) return '/booking'
  if (path.startsWith('/ai/')) return '/ai'
  if (path === '/estimate/compare') return '/estimate'
  if (RECORD_ROUTES.some(pattern => pattern.test(path))) return '/dashboard'
  url.searchParams.delete('userVehicleId')
  return path + url.search + url.hash
}

/** A booking wizard in progress: any step after the first, or the first step with its parameters. */
export function isBookingInProgress(pathname: string, search: string): boolean {
  if (pathname.startsWith('/booking/')) return true
  return pathname === '/booking' && new URLSearchParams(search).toString() !== ''
}
