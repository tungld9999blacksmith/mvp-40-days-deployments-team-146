import { Link } from 'react-router-dom'
import { Car, ChevronRight, Gauge, History, ShieldCheck } from 'lucide-react'
import type { ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import { vehicleDisplayName, warrantyComponentLabel } from '@/shared/domain/labels'
import { formatDate, formatKm, formatLicensePlate, formatNumber, formatTimeDayMonth } from '@/shared/utils/format'
import type { Odometer, VehicleProfile, VehicleSummary } from '../types'

/** Structural placeholder instead of a decorative car photo (design style §5.1). */
export function CarPlaceholder({ label, tall }: { label: string; tall?: boolean }) {
  return (
    <div className={`w-full ${tall ? 'h-40' : 'h-28'} rounded-xl bg-background border border-border flex flex-col items-center justify-center`}>
      <Car className={`${tall ? 'w-12 h-12' : 'w-9 h-9'} text-muted`} strokeWidth={1.5} aria-hidden />
      <span className="text-xs text-muted mt-2">{label}</span>
    </div>
  )
}

/** Home — vehicle summary (US-017 FE §4.3). */
export function VehicleSummaryCard({ vehicle }: { vehicle: VehicleSummary }) {
  const name = vehicleDisplayName(vehicle.modelName, vehicle.trim)
  return (
    <Card className="h-full flex flex-col">
      <CardHeader title="Xe của tôi" icon={<Car className="w-4 h-4 text-muted" />} />
      <CarPlaceholder label={name} />
      <div className="mt-4">
        <p className="text-base font-semibold text-foreground">{name}</p>
        <p className="text-sm text-muted font-mono mt-0.5">{formatLicensePlate(vehicle.licensePlate)}</p>
      </div>
      <Link
        to="/vehicle"
        className="mt-auto pt-4 inline-flex items-center gap-1 text-sm text-emerald hover:text-emerald-bright transition-colors"
      >
        Xem chi tiết <ChevronRight className="w-3.5 h-3.5" aria-hidden />
      </Link>
    </Card>
  )
}

function number(value: number | string | null, unit: string): string {
  if (value === null || value === '') return '—'
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isNaN(parsed) ? '—' : `${formatNumber(parsed)} ${unit}`
}

/** Vehicle profile — identity & specs (US-017 FE §4.4). */
export function VehicleIdentityCard({ profile }: { profile: VehicleProfile }) {
  const name = vehicleDisplayName(profile.modelName, profile.trim)
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-foreground">{name}</h2>
          <p className="text-sm text-muted font-mono mt-0.5">{formatLicensePlate(profile.licensePlate)}</p>
        </div>
        <Badge tone="success">Đã xác thực</Badge>
      </div>
      <CarPlaceholder label={name} tall />
      <div className="mt-5">
        <InfoRow label="Mẫu xe / phiên bản" value={[profile.modelName, profile.trim].filter(Boolean).join(' ') || '—'} />
        <InfoRow label="Màu" value={profile.color ?? '—'} />
        <InfoRow label="Năm sản xuất" value={profile.productionYear ?? '—'} mono />
        <InfoRow label="Số VIN" value={profile.vinMasked} mono />
        <InfoRow label="Biển số" value={formatLicensePlate(profile.licensePlate)} mono />
        <InfoRow label="Dung lượng pin" value={number(profile.batteryCapacityKwh, 'kWh')} mono />
        <InfoRow label="Công suất động cơ" value={number(profile.motorPowerKw, 'kW')} mono />
      </div>
      <p className="text-xs text-muted mt-4">
        Dữ liệu do hãng cung cấp. Nếu thông tin chưa đúng, vui lòng liên hệ hãng hoặc xưởng dịch vụ.
      </p>
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
          <p className="text-3xl font-extrabold font-mono text-foreground">
            {formatNumber(odometer.odoKm)}
            <span className="text-base font-normal text-muted ml-1">km</span>
          </p>
          <p className="text-xs text-muted mt-2">
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

export function LastServiceCard({ lastService }: { lastService: VehicleProfile['lastService'] }) {
  return (
    <Card>
      <CardHeader title="Lần bảo dưỡng gần nhất" icon={<History className="w-4 h-4 text-muted" />} />
      {lastService ? (
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-foreground">
              <span className="font-mono">{formatDate(lastService.serviceDate)}</span>
              {lastService.odoKm !== null && <span className="font-mono text-muted"> · {formatKm(lastService.odoKm)}</span>}
            </p>
            <p className="text-sm text-muted mt-1">{lastService.centerName ?? 'Xưởng dịch vụ chính hãng'}</p>
          </div>
          <Badge tone="neutral">{lastService.source === 'EV_CARE' ? 'Qua EV Care' : 'Hãng ghi nhận'}</Badge>
        </div>
      ) : (
        <p className="text-sm text-muted">Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua.</p>
      )}
    </Card>
  )
}

export function WarrantyCard({ warranties }: { warranties: VehicleProfile['warranties'] }) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 pt-5">
        <CardHeader title="Bảo hành" icon={<ShieldCheck className="w-4 h-4 text-muted" />} />
      </div>
      {warranties.length === 0 ? (
        <p className="text-sm text-muted px-5 pb-5">Chưa có thông tin bảo hành từ hãng.</p>
      ) : (
        <>
          <table className="hidden sm:table w-full text-sm">
            <thead>
              <tr className="border-y border-border">
                {['Hạng mục', 'Hết hạn', 'Giới hạn km', 'Trạng thái'].map(heading => (
                  <th key={heading} className="px-5 py-2.5 text-left text-xs font-medium text-muted">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {warranties.map(warranty => (
                <tr key={warranty.component} className="border-b border-border last:border-b-0">
                  <td className="px-5 py-3 text-foreground">{warrantyComponentLabel(warranty.component)}</td>
                  <td className="px-5 py-3 font-mono text-muted">{formatDate(warranty.endDate)}</td>
                  <td className="px-5 py-3 font-mono text-muted">{warranty.kmLimit ? formatKm(warranty.kmLimit) : 'Không giới hạn'}</td>
                  <td className="px-5 py-3">
                    <Badge tone={warranty.isActive ? 'success' : 'neutral'}>{warranty.isActive ? 'Còn hiệu lực' : 'Hết hiệu lực'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="sm:hidden px-5 pb-5 space-y-3">
            {warranties.map(warranty => (
              <li key={warranty.component} className="rounded-xl border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{warrantyComponentLabel(warranty.component)}</span>
                  <Badge tone={warranty.isActive ? 'success' : 'neutral'}>{warranty.isActive ? 'Còn hiệu lực' : 'Hết hiệu lực'}</Badge>
                </div>
                <p className="text-xs text-muted font-mono mt-1.5">
                  Đến {formatDate(warranty.endDate)} · {warranty.kmLimit ? formatKm(warranty.kmLimit) : 'Không giới hạn km'}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
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
