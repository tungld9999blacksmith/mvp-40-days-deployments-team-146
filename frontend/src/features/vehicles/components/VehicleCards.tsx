import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BatteryCharging, Car, ChevronRight, Cog, Cpu, Gauge, History, ShieldCheck, type LucideIcon } from 'lucide-react'
import type { ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import { Card, CardHeader } from '@/shared/ui/Card'
import PlateTile from '@/shared/ui/PlateTile'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { ErrorState, Notice } from '@/shared/ui/States'
import { vehicleDisplayName, warrantyComponentLabel } from '@/shared/domain/labels'
import { formatDate, formatKm, formatNumber, formatTimeDayMonth } from '@/shared/utils/format'
import type { Odometer, VehicleProfile, VehicleSummary } from '../types'
import { warrantyTimeline } from '../utils/warrantyTimeline'
import { vehiclePhotoSrc } from '../utils/vehiclePhoto'

/** Structural placeholder when there is no photo for the model (design style §5.1). */
export function CarPlaceholder({ label, tall }: { label: string; tall?: boolean }) {
  return (
    <div className={`w-full ${tall ? 'h-40' : 'h-28'} rounded-xl bg-background border border-border flex flex-col items-center justify-center`}>
      <Car className={`${tall ? 'w-12 h-12' : 'w-9 h-9'} text-muted`} strokeWidth={1.5} aria-hidden />
      <span className="text-xs text-muted mt-2">{label}</span>
    </div>
  )
}

/**
 * Photo of the model the owner declared at onboarding (a photo of the model, so the colour may differ
 * from the owner's car). Falls back to the placeholder for models without a photo or when the file fails to load.
 */
export function CarPhoto({ label, modelName, modelId, tall, fill }: {
  label: string
  modelName: string | null
  modelId?: string | null
  tall?: boolean
  /** Grow to the free height of a flex column; the whole car stays visible. */
  fill?: boolean
}) {
  const src = vehiclePhotoSrc(modelName, modelId)
  const [failed, setFailed] = useState(false)
  if (!src || failed) return <CarPlaceholder label={label} tall={tall} />

  const size = fill ? 'flex-1 min-h-36' : tall ? 'h-48' : 'h-36'
  return (
    // Photos are transparent WebP: a soft fill stages the car without a second card border or a white block in dark mode.
    <div className={`w-full ${size} overflow-hidden rounded-xl bg-card-hover`}>
      <img
        src={src}
        alt={label}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={`h-full w-full ${fill ? 'object-contain' : 'object-cover'}`}
      />
    </div>
  )
}

/** Home — vehicle summary (US-017 FE §4.3). */
export function VehicleSummaryCard({ vehicle }: { vehicle: VehicleSummary }) {
  const name = vehicleDisplayName(vehicle.modelName, vehicle.trim)
  return (
    <Card className="h-full flex flex-col">
      <CardHeader title="Xe của tôi" icon={<Car className="w-4 h-4 text-muted" />} />
      <CarPhoto label={name} modelName={vehicle.modelName} fill />
      <div className="mt-4">
        <p className="text-base font-semibold text-foreground">{name}</p>
        <PlateTile plate={vehicle.licensePlate} className="mt-2" />
      </div>
      <Link
        to="/vehicle"
        className="pt-4 inline-flex items-center gap-1 text-sm text-emerald hover:text-emerald-bright transition-colors"
      >
        Xem chi tiết <ChevronRight className="w-3.5 h-3.5" aria-hidden />
      </Link>
    </Card>
  )
}

/** Current ODO from the manufacturer — read-only, no edit (BR-003, AC-005). */
export function OdometerCard({ odometer }: { odometer: Odometer | null }) {
  return (
    <Card>
      <CardHeader title="Số km hiện tại" icon={<Gauge className="w-4 h-4 text-muted" />} />
      {odometer ? (
        <>
          <p className="font-plate text-5xl font-bold leading-none text-foreground">
            {formatNumber(odometer.odoKm)}
            <span className="text-xl text-muted ml-1.5">km</span>
          </p>
          <p className="text-xs text-muted mt-2.5">
            Hãng cập nhật lúc <span className="font-mono">{formatTimeDayMonth(odometer.recordedAt)}</span>
          </p>
          {odometer.isStale && (
            <Notice tone="warning" className="mt-3">
              Số km được hãng cập nhật lần cuối ngày {formatDate(odometer.recordedAt)}, có thể chưa phản ánh hiện tại.
            </Notice>
          )}
        </>
      ) : (
        <p className="text-sm text-muted">Hãng chưa có dữ liệu số km.</p>
      )}
    </Card>
  )
}

const WEEKDAY_SHORT = new Intl.DateTimeFormat('vi-VN', { weekday: 'short', timeZone: 'Asia/Ho_Chi_Minh' })

/** Calendar-page tile: weekday strip, day, month/year. */
function DayTile({ date }: { date: string }) {
  const [year, month, day] = date.slice(0, 10).split('-')
  return (
    <div className="w-[60px] flex-shrink-0 rounded-xl overflow-hidden border border-border text-center" aria-hidden>
      <p className="bg-foreground text-background text-[11px] font-bold py-0.5">{WEEKDAY_SHORT.format(new Date(`${date.slice(0, 10)}T12:00:00+07:00`))}</p>
      <p className="font-plate text-[26px] font-bold leading-tight text-foreground pt-0.5">{day}</p>
      <p className="text-[10px] text-muted pb-1">
        {month}/{year}
      </p>
    </div>
  )
}

export function LastServiceCard({ lastService }: { lastService: VehicleProfile['lastService'] }) {
  return (
    <Card className="flex flex-col">
      <CardHeader title="Lần bảo dưỡng gần nhất" icon={<History className="w-4 h-4 text-muted" />} />
      {lastService ? (
        <div className="flex items-center gap-3.5">
          <DayTile date={lastService.serviceDate} />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-foreground">{lastService.centerName ?? 'Xưởng dịch vụ chính hãng'}</p>
            <p className="text-xs text-muted">
              <span className="font-mono">{formatDate(lastService.serviceDate)}</span>
              {lastService.odoKm !== null && <span className="font-mono"> · {formatKm(lastService.odoKm)}</span>}
            </p>
            <Badge tone="neutral">{lastService.source === 'EV_CARE' ? 'Qua EV Care' : 'Hãng ghi nhận'}</Badge>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted">Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua.</p>
      )}
      <Link
        to="/history"
        className="mt-auto pt-4 inline-flex items-center gap-1 text-sm font-medium text-emerald hover:text-emerald-bright transition-colors"
      >
        Xem lịch sử dịch vụ <ChevronRight className="w-3.5 h-3.5" aria-hidden />
      </Link>
    </Card>
  )
}

const WARRANTY_ICONS: Record<string, LucideIcon> = {
  BATTERY: BatteryCharging,
  MOTOR: Cog,
  CHASSIS: Car,
  ELECTRONICS: Cpu,
}

const TIMELINE_BADGE = {
  active: { tone: 'success', label: 'Còn hiệu lực' },
  ending: { tone: 'warning', label: 'Sắp hết hạn' },
  ended: { tone: 'neutral', label: 'Hết hiệu lực' },
} as const

/** One tile per warranty line; the bar shows time used, the backend's `isActive` decides the status. */
export function WarrantyCard({ warranties }: { warranties: VehicleProfile['warranties'] }) {
  const now = new Date()
  const activeCount = warranties.filter(warranty => warranty.isActive).length
  return (
    <Card>
      <CardHeader
        title="Bảo hành"
        action={warranties.length > 0 ? <span className="text-xs text-muted">{activeCount}/{warranties.length} hạng mục còn hiệu lực</span> : <ShieldCheck className="w-4 h-4 text-muted" />}
      />
      {warranties.length === 0 ? (
        <p className="text-sm text-muted">Chưa có thông tin bảo hành từ hãng.</p>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {warranties.map(warranty => {
            const timeline = warrantyTimeline(warranty, now)
            const badge = TIMELINE_BADGE[timeline.tone]
            const Icon = WARRANTY_ICONS[warranty.component] ?? ShieldCheck
            const label = warrantyComponentLabel(warranty.component)
            return (
              <li key={warranty.component} className="rounded-2xl bg-background p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      'w-9 h-9 rounded-xl bg-card flex items-center justify-center',
                      timeline.tone === 'ending' ? 'text-warning' : timeline.tone === 'ended' ? 'text-muted' : 'text-emerald',
                    )}
                  >
                    <Icon className="w-[18px] h-[18px]" aria-hidden />
                  </span>
                  <Badge tone={badge.tone}>{badge.label}</Badge>
                </div>
                <div>
                  <p className="text-[15px] font-bold text-foreground">{label}</p>
                  <p className="text-xs text-muted mt-0.5">
                    Đến <span className="font-mono text-foreground">{formatDate(warranty.endDate)}</span> ·{' '}
                    <span className="font-mono">{warranty.kmLimit ? formatKm(warranty.kmLimit) : 'Không giới hạn km'}</span>
                  </p>
                </div>
                <div>
                  <div
                    role="progressbar"
                    aria-label={`Thời gian bảo hành ${label} đã dùng`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(timeline.usedRatio * 100)}
                    className="h-1.5 rounded-full bg-border overflow-hidden"
                  >
                    <div
                      className={cn('h-full rounded-full', timeline.tone === 'ending' ? 'bg-warning' : timeline.tone === 'ended' ? 'bg-muted' : 'bg-emerald')}
                      style={{ width: `${timeline.usedRatio * 100}%` }}
                    />
                  </div>
                  <p className={cn('text-xs font-semibold mt-1.5', timeline.tone === 'ending' ? 'text-warning' : 'text-foreground')}>{timeline.remainingText}</p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <p className="text-xs text-muted mt-4">Dữ liệu do hãng cung cấp. Nếu thông tin chưa đúng, vui lòng liên hệ hãng hoặc xưởng dịch vụ.</p>
    </Card>
  )
}

/** Card-level error that keeps the other cards usable (US-017 FE §12.2). */
export function CardError({ title, error, onRetry }: { title: string; error: ApiError; onRetry: () => void }) {
  return (
    <Card>
      <ErrorState compact title={title} description={null} traceId={error.traceId} onRetry={onRetry} />
    </Card>
  )
}

export function CardSkeleton({ lines }: { lines?: number }) {
  return <SkeletonCard lines={lines} />
}
