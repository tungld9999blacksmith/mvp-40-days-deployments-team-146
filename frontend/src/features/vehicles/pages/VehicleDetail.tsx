import { useEffect } from 'react'
import { track } from '@/shared/utils/track'
import Skeleton, { SkeletonCard } from '@/shared/ui/Skeleton'
import { isApiError } from '@/shared/api/client'
import MaintenanceStatusCard from '../components/MaintenanceStatusCard'
import { LastServiceCard, OdometerCard, WarrantyCard } from '../components/VehicleCards'
import VehicleHero from '../components/VehicleHero'
import VehicleGate, { VehicleApiError } from '../components/VehicleGate'
import { useMaintenanceStatus, useVehicleProfile } from '../hooks/useVehicleQueries'

const VEHICLE_ERRORS = ['VEHICLE_NOT_FOUND', 'VEHICLE_NOT_ACTIVE', 'ONBOARDING_REQUIRED']

function VehicleDetailContent({ vehicleId }: { vehicleId: string }) {
  const profile = useVehicleProfile(vehicleId)
  const status = useMaintenanceStatus(vehicleId)

  useEffect(() => {
    if (profile.data) track('vehicle_profile_viewed')
  }, [profile.data])
  useEffect(() => {
    if (status.data) {
      track('maintenance_status_viewed', {
        dueStatus: status.data.dueStatus,
        dueReason: status.data.dueReason,
        calculationBasis: status.data.calculationBasis,
        screen: 'vehicle',
      })
    }
  }, [status.data])

  const statusVehicleError = status.error && VEHICLE_ERRORS.some(code => isApiError(status.error, code))

  return (
    <div className="space-y-6">
      {profile.data ? (
        <VehicleHero profile={profile.data} status={status.data} />
      ) : profile.error ? (
        <VehicleApiError error={profile.error} onRetry={() => void profile.refetch()} title="Không tải được hồ sơ xe." />
      ) : (
        <Skeleton className="h-[420px] lg:h-80 w-full rounded-2xl" />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {statusVehicleError && status.error ? (
            <VehicleApiError error={status.error} onRetry={() => void status.refetch()} title="Không tải được trạng thái bảo dưỡng." />
          ) : (
            <MaintenanceStatusCard
              variant="full"
              status={status.data}
              error={status.error}
              onRetry={() => void status.refetch()}
              retrying={status.isFetching && status.data !== null}
              pendingSyncExhausted={status.pendingSyncExhausted}
              onRetryPendingSync={status.retryPendingSync}
            />
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-6 content-start">
          {profile.data ? (
            <>
              <OdometerCard odometer={profile.data.odometer} />
              <LastServiceCard lastService={profile.data.lastService} />
            </>
          ) : (
            !profile.error && (
              <>
                <SkeletonCard lines={2} />
                <SkeletonCard lines={3} />
              </>
            )
          )}
        </div>
      </div>

      {profile.data ? <WarrantyCard warranties={profile.data.warranties} /> : !profile.error && <SkeletonCard lines={3} />}
    </div>
  )
}

/** SCR-302 — vehicle profile, read-only; all data comes from the manufacturer (US-017 FE). */
export default function VehicleDetail() {
  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-6xl">
      {/* The hero opens the page; the heading stays for screen readers. */}
      <h1 className="sr-only">Xe của tôi</h1>
      <VehicleGate
        loading={
          <div className="space-y-6">
            <Skeleton className="h-[420px] lg:h-80 w-full rounded-2xl" />
            <SkeletonCard lines={5} />
          </div>
        }
      >
        {vehicle => <VehicleDetailContent vehicleId={vehicle.userVehicleId} />}
      </VehicleGate>
    </div>
  )
}
