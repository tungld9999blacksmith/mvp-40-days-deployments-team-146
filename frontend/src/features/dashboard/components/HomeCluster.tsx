import { useEffect, useRef, useState, type ComponentType } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CalendarCheck, Car, ChevronRight, FileClock, Gauge as GaugeIcon, ShieldCheck, Wrench } from 'lucide-react'
import Gauge from '@/shared/ui/Gauge'
import PlateTile from '@/shared/ui/PlateTile'
import { RobotMascot } from '@/shared/ui/RobotAvatar'
import { cn } from '@/shared/ui/cn'
import { isApiError } from '@/shared/api/client'
import { useTween } from '@/shared/hooks/useTween'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { formatNumber, formatTimeDayMonth } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { legacyQuotesAllowed, usePricingFlow } from '@/features/booking-lines/flow'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import { bookingsOfVehicle } from '@/features/bookings/utils'
import { useUnseenQuotes } from '@/features/quotes/hooks'
import { VehicleApiError } from '@/features/vehicles/components/VehicleGate'
import { useMaintenanceStatus, useServiceRecords, useVehicleProfile } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import { vehiclePhotoSrc } from '@/features/vehicles/utils/vehiclePhoto'
import { daysGauge, kmGauge, lastPeriodicService, tellTales, voicePrompt, type Lamp, type LampTone } from './clusterLogic'

const SELF_TEST_KEY = 'evcare.cluster.selftest'
const SELF_TEST_MS = 650

const LAMP_ICONS: Record<Lamp['id'], ComponentType<{ className?: string }>> = {
  maintenance: Wrench,
  quotes: FileClock,
  booking: CalendarCheck,
  warranty: ShieldCheck,
  odo: GaugeIcon,
}

const LAMP_ICON_TONE: Record<LampTone, string> = {
  green: 'text-banner-accent',
  amber: 'text-banner-alert',
  red: 'text-banner-danger',
  off: 'text-lamp-off',
}

/**
 * Switching the car on: on the first Home render of a browser session every lamp lights and both gauges
 * sweep to full, then settle on their values. Never under prefers-reduced-motion.
 */
function useSelfTest(ready: boolean): boolean {
  const [testing, setTesting] = useState(false)
  // Decided once per mount; StrictMode re-runs effects, and the session flag is already set the second time.
  const decided = useRef(false)
  useEffect(() => {
    if (!ready || decided.current) return
    decided.current = true
    let seen = true
    try {
      seen = sessionStorage.getItem(SELF_TEST_KEY) === '1'
      sessionStorage.setItem(SELF_TEST_KEY, '1')
    } catch {
      // Storage blocked: skip the self-test rather than replay it on every visit.
    }
    if (!seen && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) setTesting(true)
  }, [ready])
  useEffect(() => {
    if (!testing) return
    const timer = window.setTimeout(() => setTesting(false), SELF_TEST_MS)
    return () => window.clearTimeout(timer)
  }, [testing])
  return testing
}

/** ODO that rolls from the reading this browser last showed for the vehicle, only when it changed. */
function OdoReadout({ vehicleId, odoKm }: { vehicleId: string; odoKm: number }) {
  const storageKey = `evcare.odo.${vehicleId}`
  const [previous] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(storageKey))
      return Number.isFinite(saved) && saved > 0 ? saved : odoKm
    } catch {
      return odoKm
    }
  })
  const shown = useTween(odoKm, 600, previous)
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, String(odoKm))
    } catch {
      // Not remembered: the next visit simply does not roll.
    }
  }, [storageKey, odoKm])
  return (
    <p className="font-plate text-[28px] @min-[45rem]:text-[34px] font-medium leading-none">
      {formatNumber(Math.round(shown))}
      <span className="ml-1.5 font-sans text-sm text-banner-muted">km</span>
    </p>
  )
}

function CarPhoto({ src, name }: { src: string | null; name: string }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) return <Car className="w-20 h-20 text-banner-muted my-6" strokeWidth={1.25} aria-hidden />
  return (
    <img
      src={src}
      alt={`Ảnh minh hoạ ${name}`}
      decoding="async"
      onError={() => setFailed(true)}
      // The model photos carry ~15% transparent margin above and below the car.
      className="w-full max-w-[380px] h-auto object-contain -mt-6 -mb-3"
    />
  )
}

/**
 * Home cluster (DESIGN.md "HomeCluster"): km gauge · the car · days gauge, tell-tale lamps and the
 * assistant's voice bar. Every figure comes from the backend; parts without data show their empty state.
 */
export default function HomeCluster({ vehicle }: { vehicle: VehicleSummary }) {
  const vehicleId = vehicle.userVehicleId
  const status = useMaintenanceStatus(vehicleId)
  const profile = useVehicleProfile(vehicleId)
  const records = useServiceRecords(vehicleId)
  const upcoming = useUpcomingBookings()
  const unseenQuotes = useUnseenQuotes().data?.items.length ?? 0
  const quotesEnabled = legacyQuotesAllowed(usePricingFlow())

  useEffect(() => {
    if (status.data) {
      track('maintenance_status_viewed', {
        dueStatus: status.data.dueStatus,
        dueReason: status.data.dueReason,
        calculationBasis: status.data.calculationBasis,
        screen: 'home',
      })
    }
  }, [status.data])

  const testing = useSelfTest(!!status.data)

  const vehicleError =
    status.error && ['VEHICLE_NOT_FOUND', 'VEHICLE_NOT_ACTIVE', 'ONBOARDING_REQUIRED'].some(code => isApiError(status.error, code))
  if (vehicleError && status.error) {
    return (
      <div className="mb-6">
        <VehicleApiError error={status.error} onRetry={() => void status.refetch()} title="Không tải được trạng thái bảo dưỡng." />
      </div>
    )
  }

  const data = status.data
  const odometer = data?.odometer ?? profile.data?.odometer ?? null
  const nextBooking = bookingsOfVehicle(upcoming.data?.items ?? [], vehicleId)[0] ?? null
  const lastPeriodic = lastPeriodicService(records.data?.items ?? [])
  const km = kmGauge(data, lastPeriodic)
  const days = daysGauge(data, lastPeriodic)
  const lamps = tellTales({
    status: data,
    odometer,
    nextBooking,
    unseenQuotes,
    quotesEnabled,
    warranties: profile.data?.warranties ?? null,
  })
  const prompt = voicePrompt({ status: data, hasUpcomingBooking: nextBooking !== null })
  const name = vehicleDisplayName(vehicle.modelName, vehicle.trim)
  const photo = vehiclePhotoSrc(profile.data?.modelName ?? vehicle.modelName, profile.data?.modelId)

  return (
    <section aria-label="Bảng đồng hồ xe" className="@container mb-6">
      <div className="rounded-3xl border border-banner-border bg-banner text-banner-foreground px-4 py-4 @min-[45rem]:px-6 @min-[45rem]:py-5 space-y-4">
        <div className="flex items-center justify-between gap-3 text-xs text-banner-muted">
          <span className="min-w-0 truncate">
            {odometer ? (
              <>
                Dữ liệu hãng lúc <span className="font-mono text-banner-foreground">{formatTimeDayMonth(odometer.recordedAt)}</span>
              </>
            ) : status.error ? (
              <button type="button" onClick={() => void status.refetch()} className="underline underline-offset-2 hover:text-banner-foreground">
                Không tải được dữ liệu xe · Thử lại
              </button>
            ) : (
              'Đang tải dữ liệu xe…'
            )}
          </span>
          <Link to="/vehicle" className="shrink-0 inline-flex items-center gap-1 font-medium hover:text-banner-foreground">
            Chi tiết xe
            <ChevronRight className="w-3.5 h-3.5" aria-hidden />
          </Link>
        </div>

        <div className="grid grid-cols-2 items-center gap-x-3 gap-y-2 @min-[45rem]:grid-cols-[1fr_1.45fr_1fr] @min-[45rem]:gap-x-5">
          <Gauge {...km} fraction={testing && km.fraction !== null ? 1 : km.fraction} />
          <div className="col-span-2 -order-1 @min-[45rem]:col-span-1 @min-[45rem]:order-none flex flex-col items-center text-center gap-2 min-w-0">
            <CarPhoto src={photo} name={name} />
            <span aria-hidden className="w-4/5 h-px bg-banner-border" />
            <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2">
              <h2 className="font-display font-bold text-lg leading-tight">{name}</h2>
              <PlateTile plate={vehicle.licensePlate} size="sm" />
            </div>
            {odometer ? (
              <div>
                <OdoReadout vehicleId={vehicleId} odoKm={odometer.odoKm} />
                <p className="mt-1 text-[11.5px] text-banner-muted">Hãng cập nhật lúc {formatTimeDayMonth(odometer.recordedAt)}</p>
              </div>
            ) : (
              <p className="text-sm text-banner-muted">Chưa có số ODO từ hãng</p>
            )}
          </div>
          <Gauge {...days} fraction={testing && days.fraction !== null ? 1 : days.fraction} />
        </div>

        <ul aria-label="Đèn báo" className="flex flex-wrap justify-center gap-1 border-t border-banner-border pt-3">
          {lamps.map(lamp => {
            const Icon = LAMP_ICONS[lamp.id]
            const tone: LampTone = testing && lamp.tone === 'off' ? 'amber' : lamp.tone
            const lit = tone === 'amber' || tone === 'red'
            return (
              <li key={lamp.id} className={cn(lamp.tone === 'off' && 'hidden @min-[45rem]:block')}>
                <Link
                  to={lamp.to}
                  className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-xs hover:bg-banner-raised transition-colors"
                >
                  <Icon className={cn('w-4 h-4 shrink-0', LAMP_ICON_TONE[tone])} aria-hidden />
                  <span className={lit ? 'text-banner-foreground font-medium' : 'text-banner-muted'}>{lamp.label}</span>
                </Link>
              </li>
            )
          })}
        </ul>

        {prompt.kind === 'proposal' ? (
          <div className="flex flex-wrap @min-[45rem]:flex-nowrap items-center gap-3 rounded-3xl @min-[45rem]:rounded-full border border-banner-border bg-banner-raised p-2 pl-2.5">
            <span className="relative w-8 h-8 rounded-full bg-banner flex items-center justify-center shrink-0" aria-hidden>
              <RobotMascot size={26} onInk />
              <span className="absolute -right-0.5 -bottom-0.5 w-2.5 h-2.5 rounded-full bg-assistant-signal ring-2 ring-banner-raised" />
            </span>
            {/* Narrow: the sentence takes the row beside the robot and the button drops below it. */}
            <p className="grow basis-[calc(100%-2.75rem)] @min-[45rem]:basis-0 min-w-0 text-sm text-banner-muted">
              <span className="mr-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-assistant-signal">Trợ lý</span>
              <span className="text-banner-foreground">{prompt.text}</span>
            </p>
            <Link
              to={prompt.to}
              className="ml-11 @min-[45rem]:ml-0 inline-flex min-h-9 items-center gap-1.5 rounded-full bg-banner-accent px-4 text-sm font-semibold text-banner-on-accent hover:brightness-110 shrink-0"
            >
              <CalendarCheck className="w-4 h-4" aria-hidden />
              {prompt.actionLabel}
            </Link>
          </div>
        ) : (
          <Link
            to={prompt.to}
            className="group flex items-center gap-3 rounded-full border border-banner-border bg-banner-raised p-1.5 pl-2 text-sm text-banner-muted hover:border-banner-muted transition-colors"
          >
            <span className="w-8 h-8 rounded-full bg-banner flex items-center justify-center shrink-0" aria-hidden>
              <RobotMascot size={26} onInk />
            </span>
            <span className="flex-1 min-w-0 truncate">
              Hỏi xe của bạn: <span className="text-banner-foreground">“{prompt.question}”</span>
            </span>
            <span className="w-8 h-8 rounded-full border border-banner-border bg-banner flex items-center justify-center shrink-0 text-banner-foreground">
              <ArrowUpRight className="w-4 h-4 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
            </span>
          </Link>
        )}
      </div>
    </section>
  )
}
