import { apiGet, apiRequest } from '@/shared/api/client'
import type { MaintenanceStatus, ServiceRecordList, VehicleProfile, VehicleSummary, TripPlan, TripPlanInput } from './types'

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

/** API-VEH-005 — manufacturer records and EV Care visits, newest first. */
export function listServiceRecords(userVehicleId: string): Promise<ServiceRecordList> {
  return apiGet<ServiceRecordList>(`/user-vehicles/${encodeURIComponent(userVehicleId)}/service-records`, {
    timeoutMs: 10_000,
  })
}

export async function getTripPlan(vehicleId: string): Promise<{ plan: TripPlan | null }> {
  const response = await apiRequest<TripPlan | null>(`/user-vehicles/${encodeURIComponent(vehicleId)}/trip-plan`)
  return { plan: response.data }
}

export async function saveTripPlan(vehicleId: string, input: TripPlanInput): Promise<{ plan: TripPlan | null }> {
  const response = await apiRequest<TripPlan | null>(`/user-vehicles/${encodeURIComponent(vehicleId)}/trip-plan`, { method: 'PUT', body: input })
  return { plan: response.data }
}

export async function deleteTripPlan(vehicleId: string): Promise<{ plan: TripPlan | null }> {
  const response = await apiRequest<TripPlan | null>(`/user-vehicles/${encodeURIComponent(vehicleId)}/trip-plan`, { method: 'DELETE' })
  return { plan: response.data }
}
