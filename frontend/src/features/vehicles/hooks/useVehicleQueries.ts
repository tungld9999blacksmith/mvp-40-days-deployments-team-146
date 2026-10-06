import { useCallback, useEffect, useState } from 'react'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import * as vehiclesApi from '../api'

export const VEHICLES_KEY = 'vehicles'

/** API-VEH-001 — MVP: one linked vehicle, the first item. */
export function useVehicles() {
  return useCachedQuery(VEHICLES_KEY, vehiclesApi.listVehicles)
}

export function useVehicleProfile(userVehicleId: string | null) {
  const fetcher = useCallback(() => vehiclesApi.getVehicleProfile(userVehicleId as string), [userVehicleId])
  return useCachedQuery(userVehicleId ? `vehicle:${userVehicleId}` : null, fetcher)
}

/** API-VEH-005 */
export function useServiceRecords(userVehicleId: string | null) {
  const fetcher = useCallback(() => vehiclesApi.listServiceRecords(userVehicleId as string), [userVehicleId])
  return useCachedQuery(userVehicleId ? `service-records:${userVehicleId}` : null, fetcher)
}

const PENDING_SYNC_INTERVAL_MS = 5_000
const PENDING_SYNC_MAX_ATTEMPTS = 6

/**
 * API-VEH-003. While the manufacturer data is not synced yet (`UNKNOWN` +
 * `OEM_DATA_NOT_SYNCED`) it refetches every 5 s, at most 6 times (US-017 FE §9.3).
 */
export function useMaintenanceStatus(userVehicleId: string | null) {
  const fetcher = useCallback(() => vehiclesApi.getMaintenanceStatus(userVehicleId as string), [userVehicleId])
  const query = useCachedQuery(userVehicleId ? `maintenance:${userVehicleId}` : null, fetcher)
  const [attempts, setAttempts] = useState(0)
  const { data, isFetching, refetch } = query
  const pendingSync = data?.dueStatus === 'UNKNOWN' && data.unknownReason === 'OEM_DATA_NOT_SYNCED'

  useEffect(() => {
    if (!pendingSync || isFetching || attempts >= PENDING_SYNC_MAX_ATTEMPTS) return
    const timer = window.setTimeout(() => {
      setAttempts(count => count + 1)
      void refetch()
    }, PENDING_SYNC_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [pendingSync, isFetching, attempts, refetch])

  const retryPendingSync = useCallback(() => {
    setAttempts(0)
    void refetch()
  }, [refetch])

  return {
    ...query,
    pendingSync,
    pendingSyncExhausted: pendingSync && attempts >= PENDING_SYNC_MAX_ATTEMPTS,
    pendingSyncAttempts: attempts,
    retryPendingSync,
  }
}
