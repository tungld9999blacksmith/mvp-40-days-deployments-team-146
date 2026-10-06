/**
 * Entry point of the mock API, loaded lazily by `shared/api/client.ts` when `VITE_API_MOCKS`
 * is on. Groups: estimate (us-045), bookings (us-033/us-053/us-057 owner),
 * board (us-037/us-057 portal), crm (us-041). `learn` always runs with the others.
 * Demo mode adds auth + workshop-auth (us-001/005/009/013), vehicles (us-017),
 * notifications (us-021) and slots (us-029 BK-01 → 03), so no request needs the backend.
 */
import { reconcileVerification, registerAccountRoutes } from './account'
import { registerBoardRoutes } from './board'
import { registerBookingRoutes, reconcileBookings } from './bookings'
import { fail, handle, observeResponse, rewriteBody, type RequestInfo } from './core'
import { reconcileFollowUps, registerCrmRoutes } from './crm'
import { isDemo, resetDb, setDemo } from './db'
import { registerEstimateRoutes } from './estimate'
import { registerLearners } from './learn'
import { registerNotificationRoutes } from './notifications'
import { ensureSeeded } from './seed'
import { registerSlotRoutes } from './slots'
import { reconcileVehicles, registerVehicleRoutes } from './vehicles'
import { reconcileWorkshopVerification, registerWorkshopAccountRoutes } from './workshopAccount'

/** Endpoints the backend did not have (enabled by `all`). */
export const MOCK_GROUPS = ['estimate', 'bookings', 'board', 'crm'] as const
/** Endpoints the backend has; mocked in demo mode only (or when named in the list). */
export const DEMO_GROUPS = ['auth', 'workshop-auth', 'vehicles', 'notifications', 'slots'] as const

registerLearners()
registerAccountRoutes()
registerWorkshopAccountRoutes()
registerVehicleRoutes()
registerNotificationRoutes()
registerEstimateRoutes()
registerBookingRoutes()
registerSlotRoutes()
registerBoardRoutes()
registerCrmRoutes()

let isEnabled: (group: string) => boolean = () => true

export function configure(groups: readonly string[] | 'all' | 'demo') {
  setDemo(groups === 'demo')
  isEnabled = group =>
    group === 'learn' ||
    groups === 'demo' ||
    (groups === 'all' ? (MOCK_GROUPS as readonly string[]).includes(group) : groups.includes(group))
}

export async function handleRequest(info: RequestInfo): Promise<Response | null> {
  ensureSeeded()
  if (isDemo()) {
    reconcileVerification()
    reconcileWorkshopVerification()
    reconcileVehicles()
  }
  reconcileBookings()
  reconcileFollowUps()
  return handle(info, isEnabled)
}

/** Demo mode answer for an endpoint the mock does not implement (there is no backend to reach). */
export function notMocked(info: RequestInfo): Response {
  console.warn(`[mock-api] demo mode: ${info.method} ${info.path} is not mocked`)
  const { body } = fail(501, 'NOT_MOCKED', 'Chức năng này chưa có dữ liệu demo.')
  return new Response(JSON.stringify(body), { status: 501, headers: { 'Content-Type': 'application/json', 'X-Mock-Api': 'none' } })
}

export function rewriteRequest(info: RequestInfo): unknown {
  return rewriteBody(info, isEnabled)
}

export function observeRealResponse(info: RequestInfo, response: Response): Promise<void> {
  return observeResponse(info, response, isEnabled)
}

declare global {
  interface Window {
    evcareMock?: { reset: () => void }
  }
}

// Dev helper: `evcareMock.reset()` in the console clears mock data and re-seeds on next request.
if (typeof window !== 'undefined') {
  window.evcareMock = {
    reset: () => {
      resetDb()
      console.info('[mock-api] data cleared')
    },
  }
}
