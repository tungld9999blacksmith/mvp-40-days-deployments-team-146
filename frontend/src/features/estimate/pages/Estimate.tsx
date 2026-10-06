import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, CalendarClock, Car, FileText, Gauge, MapPin, PhoneCall, Star, Store } from 'lucide-react'
import { isApiError, NETWORK_ERROR } from '@/shared/api/client'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import Button from '@/shared/ui/Button'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import { SelectInput } from '@/shared/ui/Field'
import Skeleton, { SkeletonCard } from '@/shared/ui/Skeleton'
import Spinner from '@/shared/ui/Spinner'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatKm, formatLicensePlate, formatRelativeDay } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import { getCostEstimate, getMilestones } from '../api'
import { EstimateItemList, EstimateTotal } from '../components/EstimateBreakdown'
import WorkshopPickerDrawer from '../components/WorkshopPickerDrawer'
import type { ReadyEstimate } from '../types'
import { milestoneLabel, readNumberParam } from '../utils'

type ViewState =
  | { kind: 'LOADING' }
  | { kind: 'READY'; estimate: ReadyEstimate; refreshing: boolean }
  | { kind: 'NO_RULE' }
  | { kind: 'NEED_MILESTONE'; validMilestones: number[] }
  | { kind: 'NEED_WORKSHOP' }
  | { kind: 'ERROR'; code: string; traceId: string | null }

function VehicleInfo({ vehicle }: { vehicle: VehicleSummary }) {
  const status = useMaintenanceStatus(vehicle.userVehicleId)
  const odometer = status.data?.odometer ?? null
  return (
    <Card>
      <CardHeader title="Thông tin xe" icon={<Car className="w-4 h-4 text-muted" />} />
      <InfoRow label="Mẫu xe" value={[vehicle.modelName, vehicle.trim].filter(Boolean).join(' ') || '—'} />
      <InfoRow label="Biển số" value={formatLicensePlate(vehicle.licensePlate)} mono />
      <InfoRow
        label="Số km hiện tại"
        value={
          odometer ? (
            <span className="flex flex-col items-end">
              <span className="font-mono">{formatKm(odometer.odoKm)}</span>
              <span className="text-xs font-normal text-muted">Hãng cập nhật {formatRelativeDay(odometer.recordedAt)}</span>
            </span>
          ) : (
            <span className="text-muted">Chưa có dữ liệu</span>
          )
        }
      />
    </Card>
  )
}

function EstimateView({ vehicle }: { vehicle: VehicleSummary }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const odoParam = readNumberParam(searchParams.get('odoMilestone'))
  const workshopParam = searchParams.get('workshopId')
  const vehicleId = vehicle.userVehicleId

  const milestonesFetcher = useCallback(() => getMilestones(vehicleId), [vehicleId])
  const milestones = useCachedQuery(`estimate-milestones:${vehicleId}`, milestonesFetcher, 30 * 60_000)
  const [state, setState] = useState<ViewState>({ kind: 'LOADING' })
  const [pickerOpen, setPickerOpen] = useState(false)
  const [attempt, setAttempt] = useState(0)

  const update = useCallback(
    (patch: { odoMilestone?: number | null; workshopId?: string | null }) => {
      setSearchParams(
        current => {
          const next = new URLSearchParams(current)
          for (const [key, value] of Object.entries(patch)) {
            if (value === null || value === undefined) next.delete(key)
            else next.set(key, String(value))
          }
          return next
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  // `?odoMilestone=` outside API-EST-01 is dropped in favour of the next milestone (FE §8).
  const options = milestones.data?.milestones ?? []
  useEffect(() => {
    if (milestones.data && odoParam !== null && !milestones.data.milestones.some(item => item.odoMilestone === odoParam)) {
      update({ odoMilestone: null })
    }
  }, [milestones.data, odoParam, update])

  useEffect(() => {
    const controller = new AbortController()
    setState(previous => (previous.kind === 'READY' ? { ...previous, refreshing: true } : { kind: 'LOADING' }))
    getCostEstimate(vehicleId, { odoMilestone: odoParam, workshopId: workshopParam, signal: controller.signal })
      .then(result => {
        if (result.status === 'NO_RULE') {
          setState({ kind: 'NO_RULE' })
          return
        }
        setState({ kind: 'READY', estimate: result, refreshing: false })
        track('estimate_viewed', {
          odoMilestone: result.milestone.odoMilestone,
          workshopSelectedBy: result.workshop.selectedBy,
          status: result.status,
          hasReferencePrice: result.hasReferencePrice,
        })
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || (reason instanceof DOMException && reason.name === 'AbortError')) return
        if (!isApiError(reason)) {
          setState({ kind: 'ERROR', code: 'UNKNOWN', traceId: null })
          return
        }
        switch (reason.code) {
          case 'MILESTONE_REQUIRED':
          case 'MILESTONE_NOT_FOUND': {
            const valid = reason.details?.validMilestones
            setState({ kind: 'NEED_MILESTONE', validMilestones: Array.isArray(valid) ? (valid as number[]) : [] })
            if (reason.code === 'MILESTONE_NOT_FOUND') update({ odoMilestone: null })
            return
          }
          case 'WORKSHOP_REQUIRED':
            setState({ kind: 'NEED_WORKSHOP' })
            setPickerOpen(true)
            return
          case 'WORKSHOP_NOT_FOUND':
            toast.show('Xưởng hiện không nhận khách, bạn chọn xưởng khác nhé.', 'warning')
            setState({ kind: 'NEED_WORKSHOP' })
            update({ workshopId: null })
            setPickerOpen(true)
            return
          case 'VEHICLE_NOT_FOUND':
            navigate('/dashboard', { replace: true })
            return
          default:
            setState({ kind: 'ERROR', code: reason.code, traceId: reason.traceId })
        }
      })
    return () => controller.abort()
  }, [vehicleId, odoParam, workshopParam, attempt, navigate, toast, update])

  const ready = state.kind === 'READY' ? state.estimate : null
  const currentMilestone = ready?.milestone.odoMilestone ?? odoParam
  const nextActionQuery = ready
    ? `workshopId=${encodeURIComponent(ready.workshop.workshopId)}&odoMilestone=${ready.milestone.odoMilestone}`
    : ''

  function go(action: 'BOOKING' | 'COMPARE', to: string) {
    track('estimate_next_action', { action })
    navigate(to)
  }

  const selectors = state.kind !== 'NO_RULE' && (
    <Card className="grid gap-4 sm:grid-cols-2">
      {milestones.isLoading ? (
        <Skeleton className="h-[68px] w-full" />
      ) : (
        <SelectInput
          label="Mốc bảo dưỡng"
          value={currentMilestone === null ? '' : String(currentMilestone)}
          placeholder="Chọn mốc"
          onChange={event => update({ odoMilestone: Number(event.target.value) })}
          helper={state.kind === 'NEED_MILESTONE' ? 'Chưa xác định được mốc tiếp theo, bạn chọn một mốc nhé.' : undefined}
        >
          {options.map(item => (
            <option key={item.odoMilestone} value={item.odoMilestone}>
              {milestoneLabel(item.odoMilestone, item.monthMilestone)}
              {item.isNext ? ' (Tiếp theo)' : ''}
            </option>
          ))}
        </SelectInput>
      )}
      <div>
        <p className="block text-sm font-medium text-foreground mb-1.5">Xưởng dịch vụ</p>
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="w-full flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-2.5 text-left text-sm hover:border-foreground/20 transition-colors elevation-sm"
        >
          <Store className="w-4 h-4 text-muted shrink-0" />
          <span className="flex-1 min-w-0 truncate text-foreground">{ready?.workshop.name ?? 'Chọn xưởng'}</span>
          {ready?.workshop.selectedBy === 'PREFERRED' && (
            <span className="inline-flex items-center gap-1 text-xs text-warning">
              <Star className="w-3.5 h-3.5 fill-warning" /> Ưa thích
            </span>
          )}
          {state.kind === 'READY' && state.refreshing && <Spinner />}
          <span className="text-xs text-emerald font-medium">Đổi</span>
        </button>
        {ready?.workshop.selectedBy === 'NEAREST' && (
          <p className="text-xs text-muted mt-1.5 flex items-center gap-1">
            <MapPin className="w-3 h-3" /> Đang tính theo xưởng gần bạn nhất
          </p>
        )}
      </div>
    </Card>
  )

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="xl:col-span-2 space-y-5">
        {selectors}

        {state.kind === 'LOADING' && (
          <div className="space-y-4" aria-busy>
            <SkeletonCard lines={5} />
            <SkeletonCard lines={2} />
          </div>
        )}

        {state.kind === 'NO_RULE' && (
          <Card>
            <EmptyState
              icon={<FileText className="w-5 h-5" />}
              title="Chưa thể dự toán cho mẫu xe/mốc này"
              description="EV Care chưa có định mức bảo dưỡng cho mẫu xe/mốc này nên chưa thể dự toán. Bạn có thể liên hệ xưởng để được tư vấn chi phí."
              action={
                <Button variant="secondary" icon={<PhoneCall className="w-4 h-4" />} onClick={() => setPickerOpen(true)}>
                  Liên hệ xưởng
                </Button>
              }
            />
          </Card>
        )}

        {state.kind === 'NEED_MILESTONE' && (
          <Notice tone="info" title="Bạn chọn mốc bảo dưỡng muốn xem chi phí">
            Chưa xác định được mốc tiếp theo của xe từ dữ liệu hãng.
          </Notice>
        )}

        {state.kind === 'NEED_WORKSHOP' && (
          <Card>
            <EmptyState
              icon={<Store className="w-5 h-5" />}
              title="Chưa xác định được xưởng."
              description="Bạn chọn một xưởng để xem chi phí."
              action={<Button onClick={() => setPickerOpen(true)}>Chọn xưởng</Button>}
            />
          </Card>
        )}

        {state.kind === 'ERROR' && (
          <Card>
            <ErrorState
              title={state.code === NETWORK_ERROR ? 'Không có kết nối mạng.' : 'Tạm thời chưa tính được chi phí, bạn thử lại sau ít phút.'}
              description={null}
              traceId={state.traceId}
              onRetry={() => setAttempt(count => count + 1)}
            />
          </Card>
        )}

        {ready && (
          <div className={state.kind === 'READY' && state.refreshing ? 'opacity-60 transition-opacity' : undefined}>
            <div className="space-y-4">
              <EstimateItemList estimate={ready} />
              <EstimateTotal estimate={ready} />
            </div>
          </div>
        )}

        {ready && (
          <div className="sticky sm:static bottom-0 z-10 -mx-4 sm:mx-0 px-4 sm:px-0 py-3 sm:py-0 bg-background/95 sm:bg-transparent backdrop-blur sm:backdrop-blur-none border-t border-border sm:border-0 space-y-2">
            <div className="flex flex-col sm:flex-row gap-2">
              <Button className="sm:flex-1" icon={<CalendarClock className="w-4 h-4" />} onClick={() => go('BOOKING', `/booking?${nextActionQuery}`)}>
                Đặt lịch
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
              <Link
                to={`/estimate/compare?odoMilestone=${ready.milestone.odoMilestone}&workshopIds=${encodeURIComponent(ready.workshop.workshopId)}`}
                onClick={() => track('estimate_next_action', { action: 'COMPARE' })}
                className="inline-flex items-center gap-1 font-medium text-emerald hover:text-emerald-bright"
              >
                So sánh với xưởng khác <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        )}
      </div>

      <aside className="space-y-4">
        <VehicleInfo vehicle={vehicle} />
      </aside>

      <WorkshopPickerDrawer
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        userVehicleId={vehicleId}
        selected={ready ? [ready.workshop.workshopId] : workshopParam ? [workshopParam] : []}
        onConfirm={([id]) => update({ workshopId: id })}
      />
    </div>
  )
}

/** SCR-1001 — Dự toán chi phí bảo dưỡng (`/estimate?odoMilestone=&workshopId=`). */
export default function Estimate() {
  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Chi phí bảo dưỡng</h1>
        <p className="text-muted mt-1">Xem hạng mục và chi phí ước tính của một mốc tại xưởng bạn chọn.</p>
      </div>
      <VehicleGate
        loading={
          <div className="space-y-4 max-w-3xl">
            <SkeletonCard lines={2} />
            <SkeletonCard lines={5} />
          </div>
        }
      >
        {vehicle => <EstimateView vehicle={vehicle} />}
      </VehicleGate>
    </div>
  )
}
