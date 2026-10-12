import { Outlet, useLocation } from 'react-router-dom'
import { Car, Wrench } from 'lucide-react'
import Stepper from '@/shared/ui/Stepper'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { page } from '@/shared/ui/page'
import { formatKm, formatLicensePlate } from '@/shared/utils/format'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import BookingSummaryRail from '../components/BookingSummaryRail'
import { BookingWizardProvider, useBookingWizard } from '../context/BookingWizardContext'
import { useBookingMilestone } from '../hooks/useBookingMilestone'

const STEPS = ['Xưởng', 'Ngày & giờ', 'Xác nhận']
const STEP_BY_PATH: Record<string, number> = { workshops: 0, slots: 1, confirm: 2 }

function BookingHeader() {
  const { vehicle, params } = useBookingWizard()
  const { pathname } = useLocation()
  const milestone = useBookingMilestone()
  const segment = pathname.split('/').filter(Boolean)[1] ?? ''
  const step = STEP_BY_PATH[segment]
  // With a workshop from the query (estimate / quote), step 1 is skipped (FF AF-003).
  const skippedWorkshop = Boolean(params.workshopId) && segment !== 'workshops'

  return (
    <div className="mb-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Đặt lịch bảo dưỡng</h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-sm text-muted">
          <span className="inline-flex items-center gap-1.5">
            <Car className="w-4 h-4" />
            {[vehicle.modelName, vehicle.trim].filter(Boolean).join(' ') || 'Xe của bạn'} · {formatLicensePlate(vehicle.licensePlate)}
          </span>
          {milestone !== null && (
            <span className="inline-flex items-center gap-1.5">
              <Wrench className="w-4 h-4" />
              Mốc {formatKm(milestone)}
            </span>
          )}
        </div>
      </div>
      {step !== undefined && (
        <div className="max-w-xl">
          <Stepper steps={STEPS} current={step} completed={skippedWorkshop ? Math.max(step, 1) : step} />
        </div>
      )}
    </div>
  )
}

/** `/booking/*` — resolves the owner's vehicle, then hosts the wizard steps (US-029 FE §3). */
export default function BookingLayout() {
  return (
    <div className={page()}>
      <VehicleGate
        loading={
          <div className="space-y-4 max-w-3xl">
            <SkeletonCard lines={2} />
            <SkeletonCard lines={4} />
          </div>
        }
      >
        {vehicle => (
          <BookingWizardProvider vehicle={vehicle}>
            <BookingHeader />
            {/* xl: steps in 2/3, the summary rail in 1/3 (DESIGN.md 2026-10-11). Below xl the confirm card carries the summary. */}
            <div className="xl:grid xl:grid-cols-3 xl:gap-6 xl:items-start">
              <div className="xl:col-span-2 min-w-0">
                <Outlet />
              </div>
              <BookingSummaryRail className="hidden xl:block xl:sticky xl:top-6" />
            </div>
          </BookingWizardProvider>
        )}
      </VehicleGate>
    </div>
  )
}
