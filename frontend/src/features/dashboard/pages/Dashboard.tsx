import { page } from '@/shared/ui/page'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { formatWeekdayDate } from '@/shared/utils/format'
import { useAuth } from '@/features/auth/context/AuthContext'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import HomeCluster from '../components/HomeCluster'
import RecentServiceHistory from '../components/RecentServiceHistory'
import TripCards from '../components/TripCards'

/**
 * SCR-301 — Home (DESIGN.md "Home"): greeting, the instrument cluster (gauges, car, tell-tales, voice bar),
 * the trip cards, then the latest service records.
 */
export default function Dashboard() {
  const { displayName } = useAuth()

  return (
    <div className={page()}>
      <div className="mb-6">
        <p className="text-xs font-medium text-muted first-letter:uppercase">{formatWeekdayDate(new Date())}</p>
        <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
          Xin chào{displayName ? ', ' : ''}
          {displayName && <span>{displayName}</span>}
        </h1>
      </div>

      <VehicleGate loading={<SkeletonCard lines={8} className="mb-6" />}>
        {vehicle => (
          <>
            <HomeCluster vehicle={vehicle} />
            <TripCards vehicleId={vehicle.userVehicleId} />
          </>
        )}
      </VehicleGate>

      <RecentServiceHistory />
    </div>
  )
}
