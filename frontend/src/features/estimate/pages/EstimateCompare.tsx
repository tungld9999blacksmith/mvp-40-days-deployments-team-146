import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Scale, Store } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import type { VehicleSummary } from '@/features/vehicles/types'
import { compareEstimates } from '../api'
import WorkshopPickerDrawer from '../components/WorkshopPickerDrawer'
import type { CompareResult } from '../types'
import { formatVnd, readNumberParam } from '../utils'

function CompareView({ vehicle }: { vehicle: VehicleSummary }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const odoMilestone = readNumberParam(searchParams.get('odoMilestone'))
  const ids = searchParams.getAll('workshopIds').slice(0, 3)
  const idsKey = ids.join(',')
  const [result, setResult] = useState<CompareResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(ids.length < 2)
  const [names, setNames] = useState<Record<string, string>>({})
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (ids.length < 2) {
      setResult(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    compareEstimates(vehicle.userVehicleId, odoMilestone, ids)
      .then(data => !cancelled && setResult(data))
      .catch((reason: unknown) => !cancelled && setError(isApiError(reason) ? reason : null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // `ids` is represented by `idsKey`.
  }, [vehicle.userVehicleId, odoMilestone, idsKey, attempt])

  function choose(picked: string[], pickedNames: Record<string, string>) {
    setNames(previous => ({ ...previous, ...pickedNames }))
    setSearchParams(current => {
      const next = new URLSearchParams(current)
      next.delete('workshopIds')
      for (const id of picked) next.append('workshopIds', id)
      return next
    })
    setPickerOpen(false)
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {odoMilestone ? `Mốc ${new Intl.NumberFormat('vi-VN').format(odoMilestone)} km` : 'Mốc tiếp theo'} · chọn 2–3 xưởng
        </p>
        <Button variant="secondary" size="sm" icon={<Store className="w-4 h-4" />} onClick={() => setPickerOpen(true)}>
          Chọn xưởng ({ids.length}/3)
        </Button>
      </div>

      {ids.length < 2 ? (
        <Card>
          <EmptyState
            icon={<Scale className="w-5 h-5" />}
            title="Chọn ít nhất 2 xưởng để so sánh."
            action={<Button onClick={() => setPickerOpen(true)}>Chọn xưởng</Button>}
          />
        </Card>
      ) : loading ? (
        <SkeletonCard lines={4} />
      ) : error || !result ? (
        <Card>
          <ErrorState title="Tạm thời chưa so sánh được, bạn thử lại sau ít phút." description={null} traceId={error?.traceId} onRetry={() => setAttempt(count => count + 1)} />
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th className="px-5 py-3 font-medium">Xưởng</th>
                <th className="px-5 py-3 font-medium text-right">Tổng ước tính</th>
                <th className="px-5 py-3 font-medium text-right hidden sm:table-cell">Giá tham khảo</th>
              </tr>
            </thead>
            <tbody>
              {result.estimates.map((entry, index) =>
                'error' in entry ? (
                  <tr key={entry.workshopId} className="border-b border-border last:border-0">
                    <td className="px-5 py-3.5 text-foreground">{names[entry.workshopId] ?? 'Xưởng đã chọn'}</td>
                    <td colSpan={2} className="px-5 py-3.5 text-right text-muted">
                      Không tính được cho xưởng này
                    </td>
                  </tr>
                ) : (
                  <tr key={entry.workshop.workshopId} className="border-b border-border last:border-0">
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-foreground">{entry.workshop.name}</span>
                      {index === 0 && (
                        <Badge tone="success" className="ml-2">
                          Thấp nhất
                        </Badge>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-foreground">{formatVnd(entry.chargeableTotal)}</td>
                    <td className="px-5 py-3.5 text-right text-muted hidden sm:table-cell">
                      {entry.items.filter(item => item.priceSource === 'REFERENCE_PRICE').length} mục
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          <p className="px-5 py-3 text-xs text-muted border-t border-border">
            Chi phí ước tính — chi phí thực tế có thể thay đổi khi xưởng kiểm tra xe. Thứ tự theo tổng ước tính tăng dần.
          </p>
        </Card>
      )}

      <WorkshopPickerDrawer
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        userVehicleId={vehicle.userVehicleId}
        selected={ids}
        mode="multi"
        max={3}
        onConfirm={choose}
      />
    </div>
  )
}

/** SCR-1004 `[Đề xuất — Q-1003]` — same milestone at 2–3 workshops (API-EST-03). */
export default function EstimateCompare() {
  const [searchParams] = useSearchParams()
  const back = new URLSearchParams()
  const odo = searchParams.get('odoMilestone')
  if (odo) back.set('odoMilestone', odo)
  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <Link to={`/estimate${back.toString() ? `?${back}` : ''}`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground mb-3">
        <ArrowLeft className="w-4 h-4" /> Chi phí bảo dưỡng
      </Link>
      <h1 className="text-2xl font-bold tracking-tight text-foreground mb-6">So sánh xưởng</h1>
      <VehicleGate loading={<SkeletonCard lines={4} />}>{vehicle => <CompareView vehicle={vehicle} />}</VehicleGate>
    </div>
  )
}
