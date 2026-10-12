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
import { useCurrentVehicle } from '../currentVehicle/CurrentVehicleContext'

/**
 * Resolves the owner's current vehicle before rendering vehicle screens:
 * loading / list error / empty state / unknown linked vehicle (US-017 FE §10.1, §11.2).
 */
export default function VehicleGate({
  loading,
  children,
}: {
  loading: ReactNode
  children: (vehicle: VehicleSummary) => ReactNode
}) {
  const navigate = useNavigate()
  const { resolution, error, isFetching, refetch } = useCurrentVehicle()
  useOnboardingRequiredRedirect(error)

  if (resolution === null) {
    if (error) {
      return (
        <Card>
          <ErrorState traceId={error.traceId} onRetry={() => void refetch()} retrying={isFetching} />
        </Card>
      )
    }
    return <>{loading}</>
  }

  if (resolution.kind === 'not-found') {
    return <Card><ErrorState title="Không tìm thấy xe trong liên kết." description="Hãy mở lại lời nhắc từ mục Thông báo của tài khoản." /></Card>
  }
  if (resolution.kind === 'none') {
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
  // `needs-selection`: RequireCurrentVehicle is already sending the owner to the picker.
  if (resolution.kind !== 'selected') return <>{loading}</>
  return <>{children(resolution.vehicle)}</>
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
