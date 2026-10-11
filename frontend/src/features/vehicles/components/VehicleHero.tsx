import { useState } from 'react'
import { Car } from 'lucide-react'
import PlateTile from '@/shared/ui/PlateTile'
import { cn } from '@/shared/ui/cn'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { formatNumber } from '@/shared/utils/format'
import type { MaintenanceStatus, VehicleProfile } from '../types'
import { vehiclePhotoSrc } from '../utils/vehiclePhoto'

const LABEL = 'font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-banner-muted'

function figure(value: number | string | null): string | null {
  if (value === null || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isNaN(parsed) ? null : formatNumber(parsed)
}

interface Readout {
  label: string
  value: string | null
  unit: string
  alert?: boolean
}

function milestoneReadout(status: MaintenanceStatus | null): Readout {
  const km = status && status.dueStatus !== 'UNKNOWN' ? status.remainingKm : null
  if (km === null) return { label: 'Mốc tới', value: null, unit: 'km' }
  const alerting = status?.dueStatus === 'DUE_SOON' || status?.dueStatus === 'OVERDUE'
  const kmCaused = status?.dueReason === 'KM' || status?.dueReason === 'BOTH'
  return { label: km < 0 ? 'Quá mốc' : 'Mốc tới', value: formatNumber(Math.abs(km)), unit: 'km', alert: alerting && kmCaused }
}

function HeroPhoto({ profile, name }: { profile: VehicleProfile; name: string }) {
  const src = vehiclePhotoSrc(profile.modelName, profile.modelId)
  const [failed, setFailed] = useState(false)
  if (!src || failed) return <Car className="w-24 h-24 text-banner-muted" strokeWidth={1.25} aria-hidden />
  return (
    <img
      src={src}
      alt={`Ảnh minh hoạ ${name}`}
      decoding="async"
      onError={() => setFailed(true)}
      className="relative w-full max-w-[540px] h-auto object-contain"
    />
  )
}

/**
 * Vehicle page header (SCR-302): the page's single ink panel, cockpit style like the Home banner.
 * Identity, specs and readouts come from the manufacturer; nothing here is computed.
 */
export default function VehicleHero({ profile, status }: { profile: VehicleProfile; status: MaintenanceStatus | null }) {
  const name = vehicleDisplayName(profile.modelName, profile.trim)
  const readouts: Readout[] = [
    { label: 'ODO', value: profile.odometer ? formatNumber(profile.odometer.odoKm) : null, unit: 'km' },
    milestoneReadout(status),
    { label: 'Pin', value: figure(profile.batteryCapacityKwh), unit: 'kWh' },
    { label: 'Công suất', value: figure(profile.motorPowerKw), unit: 'kW' },
  ]
  // The photo is the model's stock image, so its colour can differ from this car's (FINDING-011).
  const hasPhoto = vehiclePhotoSrc(profile.modelName, profile.modelId) !== null
  const caption = [hasPhoto && 'Ảnh minh hoạ', profile.color && `Màu xe: ${profile.color}`, profile.productionYear]
    .filter(Boolean)
    .join(' · ')

  return (
    <section aria-label="Thông tin xe" className="grid lg:grid-cols-2 rounded-2xl border border-banner-border bg-banner text-banner-foreground overflow-hidden">
      <div className="order-2 lg:order-1 p-5 sm:p-8 flex flex-col justify-between gap-6">
        <div>
          <p className={cn(LABEL, 'flex items-center gap-2')}>
            <span className="w-2 h-2 rounded-full bg-banner-accent" aria-hidden />
            Đã xác thực với hãng
          </p>
          <h2 className="mt-3 text-[28px] sm:text-[38px] font-extrabold tracking-[-0.03em] leading-[1.1]">{name}</h2>
          <div className="mt-3.5 flex flex-wrap items-center gap-3">
            <PlateTile plate={profile.licensePlate} />
            <span className="font-mono text-xs text-banner-muted">VIN {profile.vinMasked}</span>
          </div>
        </div>

        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-px rounded-2xl border border-banner-border bg-banner-border overflow-hidden">
          {readouts.map(readout => (
            <div key={readout.label} className="bg-banner px-3.5 py-3">
              <dt className={LABEL}>{readout.label}</dt>
              <dd className={cn('mt-1 font-plate text-[26px] font-bold leading-none', readout.alert && 'text-amber-400')}>
                {readout.value ?? '—'}
                {readout.value && <span className={cn('ml-1 text-sm', !readout.alert && 'text-banner-muted')}>{readout.unit}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="order-1 lg:order-2 relative flex items-center justify-center min-h-44 px-6 pt-8 pb-10 lg:p-8">
        <span aria-hidden className="absolute left-[6%] right-[10%] bottom-[22%] h-px bg-banner-border" />
        <span aria-hidden className="absolute left-[18%] right-[22%] bottom-[20%] h-3.5 rounded-full bg-black/40" />
        <HeroPhoto profile={profile} name={name} />
        {caption && <p className={cn(LABEL, 'absolute right-5 bottom-4')}>{caption}</p>}
      </div>
    </section>
  )
}
