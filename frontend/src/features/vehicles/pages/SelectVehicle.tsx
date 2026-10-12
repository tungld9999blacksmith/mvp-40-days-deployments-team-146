import { useEffect, useId, useState } from 'react'
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useAuth } from '@/features/auth/context/AuthContext'
import StandaloneHeader from '@/features/auth/components/StandaloneHeader'
import { useOnboardingRequiredRedirect } from '@/features/auth/hooks/useOnboardingRequiredRedirect'
import { Card } from '@/shared/ui/Card'
import PlateTile from '@/shared/ui/PlateTile'
import Skeleton, { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { ErrorState } from '@/shared/ui/States'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { formatLicensePlate } from '@/shared/utils/format'
import { CarPhoto } from '../components/VehicleCards'
import DueStatusBadge from '../components/DueStatusBadge'
import { useMaintenanceStatus } from '../hooks/useVehicleQueries'
import { useCurrentVehicle } from '../currentVehicle/CurrentVehicleContext'
import { returnPathAfterSwitch } from '../currentVehicle/resolve'
import { orderByUrgency } from '../utils/urgency'
import type { VehicleSummary } from '../types'

/** After the list loads, wait at most this long for the due statuses before showing the vehicles in link order. */
const ORDER_WAIT_MS = 2000

/** Loads one vehicle's due status for the ordering; the card reads the same cached query. */
function StatusProbe({ userVehicleId, onStatus }: { userVehicleId: string; onStatus: (id: string, status: string | null) => void }) {
  const status = useMaintenanceStatus(userVehicleId)
  const settled = status.data ? status.data.dueStatus : status.error ? null : undefined
  useEffect(() => {
    if (settled !== undefined) onStatus(userVehicleId, settled)
  }, [settled, userVehicleId, onStatus])
  return null
}

/**
 * Picker order (FINDING-010): most urgent first. Decided once, when every status has settled or
 * after `ORDER_WAIT_MS`, so cards never move under the owner's finger; later vehicles go last.
 */
function useUrgencyOrder(vehicles: VehicleSummary[] | null) {
  const [statuses, setStatuses] = useState<Record<string, string | null>>({})
  const [timedOut, setTimedOut] = useState(false)
  const [order, setOrder] = useState<string[] | null>(null)
  const [onStatus] = useState(() => (id: string, status: string | null) => setStatuses(previous => ({ ...previous, [id]: status })))

  const loaded = vehicles !== null
  useEffect(() => {
    if (!loaded) return
    const timer = window.setTimeout(() => setTimedOut(true), ORDER_WAIT_MS)
    return () => window.clearTimeout(timer)
  }, [loaded])

  const settled = vehicles !== null && (timedOut || vehicles.every(vehicle => vehicle.userVehicleId in statuses))
  useEffect(() => {
    if (vehicles && settled && !order) setOrder(orderByUrgency(vehicles, statuses).map(vehicle => vehicle.userVehicleId))
  }, [vehicles, settled, order, statuses])

  const sorted =
    vehicles && order
      ? [...vehicles].sort((a, b) => rankIn(order, a.userVehicleId) - rankIn(order, b.userVehicleId))
      : null
  return { sorted, onStatus }
}

const rankIn = (order: string[], id: string) => (order.includes(id) ? order.indexOf(id) : order.length)

/** Due status of one card; a failed status only hides the badge, the card stays selectable. */
function VehicleDueBadge({ userVehicleId }: { userVehicleId: string }) {
  const status = useMaintenanceStatus(userVehicleId)
  if (status.data) return <DueStatusBadge status={status.data.dueStatus} />
  if (status.error) return null
  return <Skeleton className="h-6 w-28 rounded-full" />
}

function VehicleChoice({ vehicle, current, onSelect }: { vehicle: VehicleSummary; current: boolean; onSelect: () => void }) {
  const name = vehicleDisplayName(vehicle.modelName, vehicle.trim)
  const statusId = useId()
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={current || undefined}
      aria-label={`${name}, biển số ${formatLicensePlate(vehicle.licensePlate)}${current ? ', đang xem' : ''}`}
      // The label overrides the content, so the due status (what tells the cars apart) is read as the description.
      aria-describedby={statusId}
      className={cn(
        // Phones: a compact row (thumbnail beside the details) so every vehicle fits the first screen.
        'flex items-center gap-4 sm:flex-col sm:items-stretch sm:gap-0 text-left bg-card border rounded-2xl elevation-sm p-4 transition-colors hover:bg-card-hover',
        current ? 'border-emerald ring-1 ring-emerald' : 'border-border hover:border-foreground/15',
      )}
    >
      <div className="w-28 shrink-0 sm:w-full [&>div]:h-20 sm:[&>div]:h-36">
        <CarPhoto label={name} modelName={vehicle.modelName} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col sm:mt-4">
        <p className="text-base font-semibold text-foreground">{name}</p>
        <PlateTile plate={vehicle.licensePlate} size="sm" className="mt-2 self-start" />
        <div className="mt-3 flex items-center justify-between gap-3">
          <div id={statusId} className="min-h-6">
            <VehicleDueBadge userVehicleId={vehicle.userVehicleId} />
          </div>
          {current && <span className="shrink-0 text-xs font-semibold text-emerald">Đang xem</span>}
        </div>
      </div>
    </button>
  )
}

/** `/select-vehicle?returnTo=` — an owner with several vehicles picks the one the owner screens show. */
export default function SelectVehicle() {
  const { user, logout } = useAuth()
  const { vehicles, current, select, error, isFetching, refetch } = useCurrentVehicle()
  const navigate = useNavigate()
  const location = useLocation()
  const returnTo = useSearchParams()[0].get('returnTo')
  const { sorted, onStatus } = useUrgencyOrder(vehicles)
  useOnboardingRequiredRedirect(error)

  // One vehicle or none: nothing to pick, the dashboard handles both.
  if (vehicles && vehicles.length < 2) return <Navigate to="/dashboard" replace />

  const choose = (userVehicleId: string) => {
    select(userVehicleId)
    navigate(returnPathAfterSwitch(returnTo), { replace: true })
  }
  // Opened from the header: go back without switching; a direct visit has no history to go back to.
  const back = () => (location.key === 'default' ? navigate(returnPathAfterSwitch(returnTo), { replace: true }) : navigate(-1))

  return (
    <div className="min-h-screen bg-background">
      <StandaloneHeader
        width="max-w-5xl"
        label={<span className="hidden sm:inline text-muted text-sm">· Chọn xe</span>}
        email={user?.email}
        onLogout={logout}
      />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        {current && (
          <button type="button" onClick={back} className="-ml-1 mb-4 inline-flex min-h-11 items-center gap-1.5 px-1 text-sm text-muted hover:text-foreground">
            <ArrowLeft className="w-4 h-4" /> Quay lại
          </button>
        )}
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Chọn xe bạn muốn xem</h1>
        <p className="mt-1 text-sm text-muted">
          {vehicles ? `Bạn có ${vehicles.length} xe đã liên kết. Bạn có thể đổi xe bất cứ lúc nào trên thanh tiêu đề.` : 'Đang tải danh sách xe…'}
        </p>

        <div className="mt-6">
          {vehicles && !sorted && vehicles.map(vehicle => <StatusProbe key={vehicle.userVehicleId} userVehicleId={vehicle.userVehicleId} onStatus={onStatus} />)}
          {sorted ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {sorted.map(vehicle => (
                <VehicleChoice
                  key={vehicle.userVehicleId}
                  vehicle={vehicle}
                  current={vehicle.userVehicleId === current?.userVehicleId}
                  onSelect={() => choose(vehicle.userVehicleId)}
                />
              ))}
            </div>
          ) : error ? (
            <Card>
              <ErrorState title="Không tải được danh sách xe." traceId={error.traceId} onRetry={() => void refetch()} retrying={isFetching} />
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy>
              <SkeletonCard lines={3} />
              <SkeletonCard lines={3} />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
