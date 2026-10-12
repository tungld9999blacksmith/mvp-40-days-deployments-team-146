import type { DueStatus } from '../types'

const RANK: Partial<Record<string, number>> = { OVERDUE: 0, DUE_SOON: 1, NORMAL: 2 } satisfies Partial<Record<DueStatus, number>>
const LAST = 3

/**
 * Vehicles most in need of service first: overdue, due soon, normal, then unknown or failed
 * statuses (`null`, missing or a value this app does not know). Link order is kept inside a group (FINDING-010).
 */
export function orderByUrgency<T extends { userVehicleId: string }>(
  vehicles: T[],
  statuses: Partial<Record<string, DueStatus | string | null>>,
): T[] {
  const rank = (vehicle: T) => {
    const status = statuses[vehicle.userVehicleId]
    return (status ? RANK[status] : undefined) ?? LAST
  }
  return [...vehicles].sort((a, b) => rank(a) - rank(b))
}
