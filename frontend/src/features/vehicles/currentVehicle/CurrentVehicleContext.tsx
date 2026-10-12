import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Outlet, useSearchParams } from 'react-router-dom'
import type { ApiError } from '@/shared/api/client'
import { useAuth } from '@/features/auth/context/AuthContext'
import type { VehicleSummary } from '../types'
import { useVehicles } from '../hooks/useVehicleQueries'
import { resolveCurrentVehicle, type CurrentVehicleResolution } from './resolve'
import { readRememberedVehicle, rememberVehicle } from './storage'

interface CurrentVehicleValue {
  /** All ACTIVE vehicles of the owner; null until the list loads. */
  vehicles: VehicleSummary[] | null
  /** Null while the list loads or when it failed. */
  resolution: CurrentVehicleResolution | null
  current: VehicleSummary | null
  select: (userVehicleId: string) => void
  error: ApiError | null
  isFetching: boolean
  refetch: () => Promise<void>
}

const CurrentVehicleContext = createContext<CurrentVehicleValue | null>(null)

/**
 * Layout route around the owner screens: decides which of the owner's vehicles they show
 * (link > remembered pick > the only vehicle > ask on /select-vehicle).
 */
export function CurrentVehicleProvider() {
  const { user } = useAuth()
  const userId = user?.userId ?? null
  const vehicles = useVehicles()
  const [search] = useSearchParams()
  const requestedId = search.get('userVehicleId')
  // Mirrors the stored pick so it still holds for this tab when storage is blocked.
  const [memoryPick, setMemoryPick] = useState<{ userId: number; id: string | null } | null>(null)

  const rememberedId =
    userId === null ? null : memoryPick?.userId === userId ? memoryPick.id : readRememberedVehicle(userId)

  const select = useCallback(
    (userVehicleId: string | null) => {
      if (userId === null) return
      rememberVehicle(userId, userVehicleId)
      setMemoryPick({ userId, id: userVehicleId })
    },
    [userId],
  )

  const resolution = useMemo(
    () => (vehicles.data ? resolveCurrentVehicle({ vehicles: vehicles.data, requestedId, rememberedId }) : null),
    [vehicles.data, requestedId, rememberedId],
  )

  useEffect(() => {
    if (!vehicles.data || !resolution) return
    // A link to one of the owner's vehicles makes it the current one (notifications, reminders).
    if (resolution.kind === 'selected' && resolution.source === 'query' && resolution.vehicle.userVehicleId !== rememberedId) {
      select(resolution.vehicle.userVehicleId)
      return
    }
    // The remembered vehicle was unlinked: forget it.
    if (rememberedId && !vehicles.data.some(vehicle => vehicle.userVehicleId === rememberedId)) select(null)
  }, [vehicles.data, resolution, rememberedId, select])

  const value = useMemo<CurrentVehicleValue>(
    () => ({
      vehicles: vehicles.data,
      resolution,
      current: resolution?.kind === 'selected' ? resolution.vehicle : null,
      select,
      error: vehicles.error,
      isFetching: vehicles.isFetching,
      refetch: vehicles.refetch,
    }),
    [vehicles.data, vehicles.error, vehicles.isFetching, vehicles.refetch, resolution, select],
  )

  return (
    <CurrentVehicleContext.Provider value={value}>
      <Outlet />
    </CurrentVehicleContext.Provider>
  )
}

export function useCurrentVehicle(): CurrentVehicleValue {
  const value = useContext(CurrentVehicleContext)
  if (!value) throw new Error('useCurrentVehicle must be used inside CurrentVehicleProvider')
  return value
}
