import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CalendarPlus, ChevronRight } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { cn } from '@/shared/ui/cn'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { warrantyComponentLabel } from '@/shared/domain/labels'
import { formatNumber } from '@/shared/utils/format'
import { QUICK_BOOKING_ENTRY_PATH } from '@/features/assistant/quickBooking/entry'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import { bookingsOfVehicle } from '@/features/bookings/utils'
import { formatVnd } from '@/features/estimate/utils'
import { useMaintenanceStatus, useServiceRecords, useVehicleProfile } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleProfile } from '@/features/vehicles/types'
import { milestoneTitle, remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import { warrantyTimeline } from '@/features/vehicles/utils/warrantyTimeline'
import { bookingWhen, monthlySpend } from './clusterLogic'

const BUTTON = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition-colors'

function TripCard({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="bg-card border border-border rounded-2xl elevation-sm p-5 flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function CardLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex items-center gap-0.5 text-xs font-medium text-emerald hover:text-emerald-bright">
      {children}
      <ChevronRight className="w-3.5 h-3.5" aria-hidden />
    </Link>
  )
}

/** "Lịch hẹn tới": the vehicle's next appointment, or the milestone and the way to book it. */
function NextBookingCard({ vehicleId }: { vehicleId: string }) {
  const upcoming = useUpcomingBookings()
  const status = useMaintenanceStatus(vehicleId).data
  const next = bookingsOfVehicle(upcoming.data?.items ?? [], vehicleId)[0] ?? null

  if (next) {
    const badge = BOOKING_STATUS[next.status]
    return (
      <TripCard title="Lịch hẹn tới" action={<CardLink to={`/bookings/${encodeURIComponent(next.bookingId)}?src=APP`}>Xem vé</CardLink>}>
        <p className="font-plate text-[28px] font-semibold leading-none text-foreground">{bookingWhen(next)}</p>
        <p className="text-sm text-muted truncate">{next.workshop.name}</p>
        {badge && <Badge tone={badge.tone} className="self-start">{badge.label}</Badge>}
      </TripCard>
    )
  }

  const milestone = status && status.dueStatus !== 'UNKNOWN' ? status.nextMilestone : null
  const remaining = status && milestone ? remainingParts(status).map(part => part.text).join(' · ') : ''
  return (
    <TripCard title="Lịch hẹn tới">
      <p className="font-plate text-[28px] font-semibold leading-none text-foreground">Chưa có</p>
      <p className="text-sm text-muted">
        {milestone ? `${milestoneTitle(milestone)}${remaining ? `: ${remaining.charAt(0).toLowerCase()}${remaining.slice(1)}` : ''}.` : 'Đặt lịch tại xưởng VinFast gần bạn.'}
      </p>
      <div className="mt-auto flex flex-wrap gap-2">
        <Link to={QUICK_BOOKING_ENTRY_PATH} className={cn(BUTTON, 'bg-brand text-on-brand hover:bg-emerald-bright')}>
          <CalendarPlus className="w-4 h-4" aria-hidden />
          Đặt lịch
        </Link>
        <Link
          to={milestone ? `/estimate?odoMilestone=${milestone.odoMilestoneKm}` : '/estimate'}
          className={cn(BUTTON, 'border border-border bg-card text-foreground hover:bg-card-hover')}
        >
          Ước tính chi phí
        </Link>
      </div>
    </TripCard>
  )
}

/** EV Care spend per month, bars drawn to scale from 0 to the year's largest month. */
function SpendCard({ vehicleId }: { vehicleId: string }) {
  const records = useServiceRecords(vehicleId)
  const spend = monthlySpend(records.data?.items ?? [])
  const lastPaid = [...spend.months].reverse().find(month => month.total > 0)?.key ?? null

  return (
    <TripCard title="Chi phí qua EV Care · 12 tháng" action={<CardLink to="/history">Chi tiết</CardLink>}>
      <p className="font-plate text-[28px] font-semibold leading-none text-foreground">
        {formatNumber(spend.total)}
        <span className="ml-1 font-sans text-sm font-medium text-muted">₫</span>
      </p>
      {spend.total === 0 ? (
        <p className="text-sm text-muted">{records.data ? 'Chưa có lần bảo dưỡng nào có chi phí qua EV Care trong 12 tháng qua.' : 'Đang tải…'}</p>
      ) : (
        <figure className="mt-1" aria-label={`Chi phí theo tháng, tổng ${formatVnd(spend.total)}`}>
          <div className="relative h-24 grid grid-cols-12 items-end gap-1 border-b border-border">
            <span aria-hidden className="absolute inset-x-0 top-1/2 border-t border-dashed border-border" />
            {spend.months.map(month => (
              <span
                key={month.key}
                title={`Tháng ${month.label}: ${formatVnd(month.total)}`}
                className={cn(
                  'relative rounded-t-[3px]',
                  month.total === 0 ? 'h-0.5 bg-border' : month.key === lastPaid ? 'bg-brand' : 'bg-muted/40',
                )}
                style={month.total > 0 ? { height: `${(month.total / spend.max) * 100}%` } : undefined}
              />
            ))}
          </div>
          <figcaption className="mt-1 grid grid-cols-12 gap-1 text-center font-mono text-[10px] text-muted">
            {spend.months.map(month => (
              <span key={month.key}>{month.label}</span>
            ))}
          </figcaption>
        </figure>
      )}
    </TripCard>
  )
}

function figure(value: number | string | null): string | null {
  if (value === null || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isNaN(parsed) ? null : formatNumber(parsed)
}

/** The warranty line to show: battery first (the owner's biggest worry), else the one that ends last. */
function headlineWarranty(profile: VehicleProfile) {
  const lines = profile.warranties
  return lines.find(line => line.component === 'BATTERY') ?? [...lines].sort((a, b) => b.endDate.localeCompare(a.endDate))[0] ?? null
}

/** Specs from the manufacturer and the headline warranty with its time-used bar (display only). */
function SpecsCard({ vehicleId }: { vehicleId: string }) {
  const profile = useVehicleProfile(vehicleId).data
  const rows = profile
    ? [
        { label: 'Dung lượng pin', value: figure(profile.batteryCapacityKwh), unit: 'kWh' },
        { label: 'Công suất', value: figure(profile.motorPowerKw), unit: 'kW' },
        { label: 'Năm sản xuất', value: profile.productionYear ? String(profile.productionYear) : null, unit: '' },
      ].filter(row => row.value !== null)
    : []
  const warranty = profile ? headlineWarranty(profile) : null
  const timeline = warranty ? warrantyTimeline(warranty) : null

  return (
    <TripCard title="Thông số & bảo hành" action={<CardLink to="/vehicle">Xe của tôi</CardLink>}>
      {!profile ? (
        <p className="text-sm text-muted">Đang tải…</p>
      ) : (
        <>
          {rows.length > 0 && (
            <dl className="divide-y divide-border">
              {rows.map(row => (
                <div key={row.label} className="flex items-baseline justify-between gap-3 py-2 first:pt-0">
                  <dt className="text-sm text-muted">{row.label}</dt>
                  <dd className="font-plate text-base font-semibold text-foreground">
                    {row.value}
                    {row.unit && <span className="ml-1 font-sans text-xs text-muted">{row.unit}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {warranty && timeline && (
            <div className="mt-auto">
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="text-muted">Bảo hành {warrantyComponentLabel(warranty.component).toLowerCase()}</span>
                <span className={cn('font-medium', timeline.tone === 'ending' ? 'text-warning' : timeline.tone === 'ended' ? 'text-muted' : 'text-foreground')}>
                  {timeline.remainingText}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-full bg-background border border-border overflow-hidden" aria-hidden>
                <div
                  className={cn('h-full', timeline.tone === 'ending' ? 'bg-warning' : timeline.tone === 'ended' ? 'bg-muted' : 'bg-brand')}
                  style={{ width: `${Math.round(timeline.usedRatio * 100)}%` }}
                />
              </div>
            </div>
          )}
        </>
      )}
    </TripCard>
  )
}

/** Home, under the cluster: next appointment, EV Care spend, specs and warranty (DESIGN.md "Trip cards"). */
export default function TripCards({ vehicleId }: { vehicleId: string }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-6 mb-6">
      <NextBookingCard vehicleId={vehicleId} />
      <SpendCard vehicleId={vehicleId} />
      <SpecsCard vehicleId={vehicleId} />
    </div>
  )
}
