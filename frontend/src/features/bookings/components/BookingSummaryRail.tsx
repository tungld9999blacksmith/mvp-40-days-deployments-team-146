import { useLocation, useNavigate } from 'react-router-dom'
import { CalendarClock, Car, Check, ShieldCheck, Store, Wrench } from 'lucide-react'
import { Card, CardHeader } from '@/shared/ui/Card'
import PlateTile from '@/shared/ui/PlateTile'
import RailRow from '@/shared/ui/RailRow'
import Skeleton from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { formatKm } from '@/shared/utils/format'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import { remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import { useBookingWizard } from '../context/BookingWizardContext'
import { useBookingMilestone } from '../hooks/useBookingMilestone'
import { formatLongDay, milestoneItemsFor, slotLabel } from '../utils'

function ChangeButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="text-xs font-medium text-emerald hover:text-emerald-bright">
      Đổi
    </button>
  )
}

/**
 * Right rail of the booking wizard (xl and up): what is being booked, filled in step by step.
 * The cost stays on the confirm card, which is the only place that knows it.
 */
export default function BookingSummaryRail({ className }: { className?: string }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { vehicle, params, card, searchFor, workshopById } = useBookingWizard()
  const status = useMaintenanceStatus(vehicle.userVehicleId)
  const milestone = useBookingMilestone()

  const step = pathname.split('/').filter(Boolean)[1] ?? ''
  const next = status.data?.nextMilestone ?? null
  const items = milestoneItemsFor(next, params.odoMilestone)
  // Remaining km / days belong to the next milestone only.
  const remaining = status.data && next && milestone === next.odoMilestoneKm ? remainingParts(status.data) : []
  const workshopId = card?.workshopId ?? params.workshopId
  const workshop = workshopById(workshopId)
  // On the workshop list the date is only a filter; it counts once the slot grid is open.
  const day = card?.date ?? (step === 'slots' ? params.date : null)

  return (
    <aside className={className} aria-label="Tóm tắt lịch hẹn">
      <Card>
        <CardHeader title="Tóm tắt lịch hẹn" />
        <div>
          <RailRow icon={<Car />} label="Xe">
            <span className="block">{[vehicle.modelName, vehicle.trim].filter(Boolean).join(' ') || 'Xe của bạn'}</span>
            <PlateTile plate={vehicle.licensePlate} size="sm" className="mt-1.5" />
          </RailRow>

          <RailRow icon={<Wrench />} label="Bảo dưỡng" empty={milestone === null}>
            {milestone === null ? (
              'Theo yêu cầu, xưởng tư vấn tại chỗ'
            ) : (
              <>
                <span className="block font-mono">Mốc {formatKm(milestone)}</span>
                {remaining.length > 0 && (
                  <span className="block text-xs font-normal mt-0.5">
                    {remaining.map((part, index) => (
                      <span key={part.kind} className={cn(part.emphasized ? 'text-warning font-semibold' : 'text-muted')}>
                        {index > 0 && ' · '}
                        {part.text}
                      </span>
                    ))}
                  </span>
                )}
                {items.length > 0 && (
                  <ul className="mt-2 space-y-1.5 font-normal">
                    {items.map(item => (
                      <li key={item.itemCode} className="flex items-start gap-2 text-[13px]">
                        <Check className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald" aria-hidden />
                        <span className="flex-1 min-w-0">{item.itemName}</span>
                        {item.isCoveredByWarranty && (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald shrink-0">
                            <ShieldCheck className="w-3.5 h-3.5" aria-hidden /> Bảo hành
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </RailRow>

          <RailRow
            icon={<Store />}
            label="Xưởng"
            empty={!workshopId}
            action={
              workshopId && step !== 'workshops' ? (
                <ChangeButton onClick={() => navigate(`/booking/workshops${searchFor({ workshopId: null, timeSlot: null, quoteId: null })}`)} />
              ) : undefined
            }
          >
            {!workshopId ? (
              'Chưa chọn'
            ) : workshop ? (
              <>
                <span className="block">{workshop.name}</span>
                {workshop.address && <span className="block text-xs font-normal text-muted mt-0.5">{workshop.address}</span>}
              </>
            ) : (
              <Skeleton className="h-4 w-40" />
            )}
          </RailRow>

          <RailRow
            icon={<CalendarClock />}
            label="Thời gian"
            empty={!card}
            action={card && step === 'confirm' ? <ChangeButton onClick={() => navigate(`/booking/slots${searchFor({ timeSlot: null })}`)} /> : undefined}
          >
            {card ? (
              <span className="font-mono">
                {slotLabel(card.timeSlot)} · {formatLongDay(card.date)}
              </span>
            ) : day ? (
              `${formatLongDay(day)} · chưa chọn giờ`
            ) : (
              'Chưa chọn'
            )}
          </RailRow>
        </div>
      </Card>
    </aside>
  )
}
