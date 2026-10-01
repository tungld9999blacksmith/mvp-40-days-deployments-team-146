import { apiGet } from '@/shared/api/client'
import type { MaintenanceStatus, VehicleProfile, VehicleSummary } from './types'

/** API-VEH-001 */
export function listVehicles(): Promise<VehicleSummary[]> {
  return apiGet<VehicleSummary[]>('/user-vehicles', { timeoutMs: 10_000 })
}

/** API-VEH-002 */
export function getVehicleProfile(userVehicleId: string): Promise<VehicleProfile> {
  return apiGet<VehicleProfile>(`/user-vehicles/${encodeURIComponent(userVehicleId)}`, { timeoutMs: 10_000 })
}

/** API-VEH-003 — reads synced data only; never fails because the manufacturer is down. */
export function getMaintenanceStatus(userVehicleId: string): Promise<MaintenanceStatus> {
  return apiGet<MaintenanceStatus>(`/user-vehicles/${encodeURIComponent(userVehicleId)}/maintenance-status`, {
    timeoutMs: 10_000,
  })
}
