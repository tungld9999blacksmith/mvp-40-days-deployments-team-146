import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Car } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useOnboardingRequiredRedirect } from '@/features/auth/hooks/useOnboardingRequiredRedirect'
import { invalidateQuery } from '@/shared/hooks/useCachedQuery'
import type { VehicleSummary } from '../types'
import { useVehicles, VEHICLES_KEY } from '../hooks/useVehicleQueries'

/**
 * Resolves the owner's (single) vehicle before rendering vehicle screens:
 * loading / list error / empty state / not-active state (US-017 FE §10.1, §11.2).
 */
export default function VehicleGate({
  loading,
  children,
}: {
  loading: ReactNode
  children: (vehicle: VehicleSummary) => ReactNode
}) {
  const navigate = useNavigate()
  const vehicles = useVehicles()
  useOnboardingRequiredRedirect(vehicles.error)

  if (vehicles.data === null) {
    if (vehicles.error) {
      return (
        <Card>
          <ErrorState traceId={vehicles.error.traceId} onRetry={() => void vehicles.refetch()} retrying={vehicles.isFetching} />
        </Card>
      )
    }
    return <>{loading}</>
  }

  const vehicle = vehicles.data[0]
  if (!vehicle) {
    return (
      <Card>
        <EmptyState
          icon={<Car className="w-5 h-5" />}
          title="Bạn chưa có xe nào được liên kết."
          description="Hoàn tất xác thực xe để theo dõi lịch bảo dưỡng."
          action={<Button onClick={() => navigate('/onboarding')}>Xác thực xe</Button>}
        />
      </Card>
    )
  }
  return <>{children(vehicle)}</>
}

/** Shared handling of vehicle-level API errors (404 → reload list, 409 → not active). */
export function VehicleApiError({ error, onRetry, title }: { error: ApiError; onRetry: () => void; title: string }) {
  const navigate = useNavigate()
  const vehicles = useVehicles()
  useOnboardingRequiredRedirect(error)
  if (isApiError(error, 'VEHICLE_NOT_ACTIVE')) {
    return (
      <Card>
        <EmptyState
          icon={<Car className="w-5 h-5" />}
          title="Xe chưa được xác thực hoặc đã gỡ liên kết."
          action={<Button onClick={() => navigate('/onboarding')}>Xác thực xe</Button>}
        />
      </Card>
    )
  }
  if (isApiError(error, 'VEHICLE_NOT_FOUND')) {
    // Never reveal another owner's vehicle (AC-008): reload the owner's own list.
    return (
      <Card>
        <ErrorState
          compact
          title="Không tìm thấy thông tin xe."
          description={null}
          onRetry={() => {
            invalidateQuery(VEHICLES_KEY)
            void vehicles.refetch().then(onRetry)
          }}
        />
      </Card>
    )
  }
  return (
    <Card>
      <ErrorState compact title={title} description={null} traceId={error.traceId} onRetry={onRetry} />
    </Card>
  )
}
