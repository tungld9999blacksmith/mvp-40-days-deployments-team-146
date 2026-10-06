import { useEffect, useState } from 'react'
import { Check, MapPin, MapPinOff, Star } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Drawer from '@/shared/ui/Drawer'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { getNearbyWorkshops } from '@/features/bookings/api'
import LocationAnchorPicker from '@/features/bookings/components/LocationAnchorPicker'
import type { LocationAnchor, NearbyData } from '@/features/bookings/types'
import { formatDistance } from '@/features/bookings/utils'

interface Props {
  open: boolean
  onClose: () => void
  userVehicleId: string
  /** Currently selected workshop ids. */
  selected: string[]
  /** `single` picks one and closes; `multi` allows up to `max` (SCR-1004). */
  mode?: 'single' | 'multi'
  max?: number
  onConfirm: (workshopIds: string[], names: Record<string, string>) => void
}

/** SCR-1003 — workshops from API-BK-01 (no date) with distance and the ★ preferred mark. */
export default function WorkshopPickerDrawer({ open, onClose, userVehicleId, selected, mode = 'single', max = 3, onConfirm }: Props) {
  const [anchor, setAnchor] = useState<LocationAnchor>(null)
  const [data, setData] = useState<NearbyData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [picked, setPicked] = useState<string[]>(selected)

  useEffect(() => {
    // Start from the current selection each time the drawer opens.
    if (open) setPicked(selected)
  }, [open]) // `selected` is read only when opening

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    getNearbyWorkshops({ anchor, userVehicleId })
      .then(result => !cancelled && setData(result))
      .catch((reason: unknown) => {
        if (cancelled) return
        setData(null)
        setError(isApiError(reason) ? reason : null)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [open, anchor, userVehicleId, attempt])

  const names = Object.fromEntries((data?.workshops ?? []).map(workshop => [workshop.workshopId, workshop.name]))
  const anchorRequired = isApiError(error, 'LOCATION_ANCHOR_REQUIRED')

  function toggle(id: string) {
    if (mode === 'single') {
      onConfirm([id], names)
      onClose()
      return
    }
    setPicked(current => (current.includes(id) ? current.filter(item => item !== id) : current.length >= max ? current : [...current, id]))
  }

  return (
    <Drawer open={open} onClose={onClose} title={mode === 'multi' ? `Chọn 2–${max} xưởng để so sánh` : 'Chọn xưởng'}>
      <div className="p-5 space-y-4">
        <LocationAnchorPicker resolved={data?.anchor ?? null} value={anchor} onChange={setAnchor} forceOpen={anchorRequired} />

        {loading ? (
          <div className="space-y-3" aria-busy>
            {[0, 1, 2].map(index => (
              <Skeleton key={index} className="h-16 w-full rounded-2xl" />
            ))}
          </div>
        ) : anchorRequired ? (
          <EmptyState icon={<MapPinOff className="w-5 h-5" />} title="Cho mình biết bạn muốn tìm xưởng gần đâu nhé." />
        ) : error || !data ? (
          <ErrorState compact title="Không tải được danh sách xưởng." traceId={error?.traceId} onRetry={() => setAttempt(count => count + 1)} />
        ) : data.workshops.length === 0 ? (
          <EmptyState icon={<MapPinOff className="w-5 h-5" />} title="Chưa có xưởng khả dụng gần vị trí này." />
        ) : (
          <ul className="space-y-2" role={mode === 'multi' ? 'group' : 'listbox'} aria-label="Danh sách xưởng">
            {data.workshops.map(workshop => {
              const active = picked.includes(workshop.workshopId)
              const disabled = mode === 'multi' && !active && picked.length >= max
              return (
                <li key={workshop.workshopId}>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-pressed={mode === 'multi' ? active : undefined}
                    aria-selected={mode === 'single' ? active : undefined}
                    onClick={() => toggle(workshop.workshopId)}
                    className={cn(
                      'w-full text-left rounded-2xl border px-4 py-3 transition-colors flex items-start gap-3',
                      active ? 'border-emerald/50 bg-emerald/5' : 'border-border bg-card hover:bg-card-hover',
                      disabled && 'opacity-50 cursor-not-allowed',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 w-5 h-5 rounded-md border flex items-center justify-center shrink-0',
                        active ? 'bg-brand border-brand text-on-brand' : 'border-border',
                      )}
                      aria-hidden
                    >
                      {active && <Check className="w-3.5 h-3.5" />}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                        {workshop.isPreferred && <Star className="w-3.5 h-3.5 text-warning fill-warning shrink-0" aria-label="Ưa thích" />}
                        <span className="truncate">{workshop.name}</span>
                        {workshop.isPreferred && <span className="text-xs font-medium text-warning">Ưa thích</span>}
                      </span>
                      <span className="mt-0.5 flex items-start gap-1 text-xs text-muted">
                        <MapPin className="w-3 h-3 mt-0.5 shrink-0" />
                        {workshop.address}
                      </span>
                    </span>
                    <span className="text-xs text-muted whitespace-nowrap">{formatDistance(workshop.distanceKm)}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}

        {mode === 'multi' && (
          <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-surface border-t border-border flex items-center justify-between gap-3">
            <span className="text-xs text-muted">
              Đã chọn {picked.length}/{max}
            </span>
            <Button disabled={picked.length < 2} onClick={() => onConfirm(picked, names)}>
              So sánh
            </Button>
          </div>
        )}
      </div>
    </Drawer>
  )
}
