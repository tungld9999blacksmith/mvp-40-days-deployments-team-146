import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarClock, Car, MapPin, PackageCheck, Wrench } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { cn } from '@/shared/ui/cn'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { getAvailability } from '@/features/bookings/api'
import { SlotGrid } from '@/features/bookings/components/SlotPicker'
import type { Slot } from '@/features/bookings/types'
import { dayChip, formatLongDay, isPastSlot, slotLabel } from '@/features/bookings/utils'
import { milestoneLabel } from '@/features/estimate/utils'
import DueStatusBadge from '@/features/vehicles/components/DueStatusBadge'
import { formatDistance, formatMoney, proposalView } from '../quickBooking/proposalView'
import { useQuickBookingActions, type ProposalOutcome } from '../quickBooking/QuickBookingContext'
import type { BookingProposalCard as Card, ProposalOption } from '../types'

const MIN_LEAD_MS = 2 * 60 * 60 * 1000 // us-061 BR-1504 — display filter only, the backend re-checks
const HORIZON_DAYS = 14

function vnDay(date: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(date)
}

/** Calendar-page tile for the proposed day: weekday strip, big date, month. */
function DateTile({ date }: { date: string }) {
  const [, month, day] = date.split('-')
  return (
    <div className="w-[68px] flex-shrink-0 rounded-2xl overflow-hidden border border-border bg-card text-center" aria-hidden>
      <p className="bg-brand text-on-brand text-xs font-bold py-1">{dayChip(date).weekday}</p>
      <p className="font-plate font-bold text-[32px] leading-none text-foreground pt-1.5">{day}</p>
      <p className="text-[11px] text-muted pb-1.5">Tháng {Number(month)}</p>
    </div>
  )
}

function OptionLine({ option, locationLabel }: { option: ProposalOption; locationLabel: string | null }) {
  return (
    <>
      <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
        <MapPin className="w-3.5 h-3.5 text-emerald flex-shrink-0" aria-hidden />
        {option.workshopName}
        {option.isPreferred && <Badge tone="neutral">Xưởng yêu thích</Badge>}
      </p>
      {option.address && <p className="text-xs text-muted ml-5">{option.address}</p>}
      <p className="text-xs text-muted ml-5">
        {option.distanceKm !== null ? `Cách bạn ${formatDistance(option.distanceKm)}` : (locationLabel ?? null)}
      </p>
    </>
  )
}

const TIER_LABEL = {
  REQUIRED: 'Bắt buộc',
  RECOMMENDED: 'Khuyến nghị',
  OPTIONAL: 'Tùy chọn',
} as const

function MaintenancePackage({ option }: { option: ProposalOption }) {
  const maintenancePackage = option.maintenancePackage
  if (!maintenancePackage) return null
  return (
    <section className="rounded-2xl border border-emerald/30 bg-emerald-dim p-3 space-y-2" aria-label="Gói bảo dưỡng đã chọn">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-foreground flex items-center gap-1.5">
          <PackageCheck className="w-4 h-4 text-emerald" aria-hidden />
          Gói {maintenancePackage.name}
        </p>
        <Badge tone="neutral">{maintenancePackage.packageCode}</Badge>
      </div>
      <ul className="space-y-1">
        {maintenancePackage.items.map(item => (
          <li key={item.itemCode} className="flex justify-between gap-3 text-xs text-foreground">
            <span>{item.itemName} <span className="text-muted">· {TIER_LABEL[item.tier]}</span></span>
            <span className="font-mono whitespace-nowrap">{item.covered ? 'Bảo hành' : formatMoney(item.price)}</span>
          </li>
        ))}
      </ul>
      <div className="flex justify-between gap-3 border-t border-border pt-2 text-xs">
        <span className="text-muted">{maintenancePackage.estimatedDurationMinutes} phút dự kiến</span>
        <span className="font-mono font-semibold text-foreground">{formatMoney(maintenancePackage.estimatedTotal)}</span>
      </div>
      {maintenancePackage.pricingUpdatedForWorkshop && (
        <p className="text-[11px] text-muted">Giá đã được cập nhật theo xưởng này; phạm vi hạng mục của gói được giữ nguyên.</p>
      )}
    </section>
  )
}

/** SCR-1501 — proposal card of us-061; nothing is booked until "Xác nhận đặt lịch" (BR-1509). */
export default function BookingProposalCard({ card, confirmationHref }: { card: Card; confirmationHref?: string }) {
  const navigate = useNavigate()
  const actions = useQuickBookingActions()
  // The demo backend owns expiry when its clock is shifted for a service walkthrough.
  const view = proposalView(card, confirmationHref ? new Date(0) : undefined)
  const [working, setWorking] = useState<'confirm' | 'revise' | 'cancel' | null>(null)
  const [outcome, setOutcome] = useState<Exclude<ProposalOutcome, { ok: true }> | null>(null)
  const [changing, setChanging] = useState(false)
  const primary = card.primary
  const disabled = working !== null || (!confirmationHref && (!actions || actions.busy))

  async function run(kind: 'confirm' | 'revise' | 'cancel', task: () => Promise<ProposalOutcome>) {
    setWorking(kind)
    setOutcome(null)
    try {
      const result = await task()
      if (!result.ok) setOutcome(result)
      else setChanging(false)
    } finally {
      setWorking(null)
    }
  }

  return (
    <div className="mt-4 rounded-[20px] border border-border bg-card overflow-hidden" aria-label="Đề xuất đặt lịch">
      <div className="flex items-center justify-between gap-2 px-4 py-3 bg-emerald-dim">
        <p className="text-sm font-bold text-emerald-bright flex items-center gap-2">
          <CalendarClock className="w-4 h-4" aria-hidden /> Đề xuất đặt lịch
        </p>
        <Badge tone={view.badge.tone}>{view.badge.label}</Badge>
      </div>

      <div className="p-4 space-y-3">
      <p className="text-xs text-muted flex items-center gap-1.5">
        <Car className="w-3.5 h-3.5" aria-hidden />
        {vehicleDisplayName(card.vehicle.modelName, card.vehicle.trim)}
        {card.vehicle.licensePlateMasked && <span className="font-mono">· {card.vehicle.licensePlateMasked}</span>}
      </p>

      {card.milestone && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">
              {milestoneLabel(card.milestone.odoMilestoneKm, card.milestone.monthMilestone)}
            </span>
            <DueStatusBadge status={card.milestone.dueStatus} />
          </div>
          <ul className="text-xs text-foreground space-y-0.5">
            {card.milestone.items.map(item => (
              <li key={item.itemCode} className="flex items-center gap-1.5">
                <Wrench className="w-3 h-3 text-muted flex-shrink-0" aria-hidden />
                {item.itemName}
                {item.isCoveredByWarranty && <span className="text-emerald">· Bảo hành</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {card.reason && <p className="text-xs text-muted leading-relaxed">{card.reason}</p>}

      <div className={cn('rounded-2xl bg-background p-3.5 space-y-3', view.status !== 'PROPOSED' && view.status !== 'CONFIRMED' && 'opacity-60')}>
        <div className="flex items-center gap-3.5">
          <DateTile date={primary.date} />
          <div className="min-w-0 space-y-0.5">
            <p className="font-plate font-bold text-[30px] leading-none text-foreground">{slotLabel(primary.timeSlot)}</p>
            <p className="text-[13px] font-medium text-foreground">{formatLongDay(primary.date)}</p>
          </div>
        </div>
        <div className="space-y-0.5">
          <OptionLine option={primary} locationLabel={card.locationLabel} />
        </div>
        {primary.estimate && (
          <p className="text-xs ml-5">
            <span className="text-muted">Chi phí ước tính: </span>
            <span className="font-mono font-semibold text-foreground">{formatMoney(primary.estimate.chargeableTotal)}</span>
            {primary.estimate.hasReferencePrice && <span className="text-muted"> · Giá tham khảo, xưởng có thể báo khác</span>}
          </p>
        )}
        <MaintenancePackage option={primary} />
      </div>

      {view.code && (
        <p className="text-sm text-foreground">
          Mã đặt lịch <span className="font-mono font-semibold text-emerald">{view.code}</span>
        </p>
      )}
      {view.note && <p className="text-xs text-muted">{confirmationHref ? 'Đề xuất giữ trong 10 phút, chưa giữ chỗ. Hệ thống kiểm tra lại trước khi bạn xác nhận.' : view.note}</p>}

      {outcome && (
        <p role="alert" className="text-xs text-error">
          {outcome.message}{' '}
          {outcome.bookingId && (
            <Link to={`/bookings/${encodeURIComponent(outcome.bookingId)}`} className="underline">
              Xem lịch hẹn
            </Link>
          )}
        </p>
      )}

      {changing && actions && view.actions.length > 0 && (
        <ChangePanel
          card={card}
          busy={working === 'revise'}
          onPick={choice => run('revise', () => actions.revise(card.proposalId, choice))}
          onClose={() => setChanging(false)}
        />
      )}

      {(actions || confirmationHref) && view.actions.length > 0 && !changing && (
        <div className="flex flex-col min-[400px]:flex-row gap-2 pt-1">
          <Button
            size="sm"
            loading={working === 'confirm'}
            disabled={disabled}
            onClick={() => confirmationHref ? navigate(confirmationHref) : run('confirm', () => actions!.confirm(card.proposalId))}
          >
            {outcome?.retryable ? 'Thử lại' : 'Xác nhận đặt lịch'}
          </Button>
          <Button size="sm" variant="secondary" disabled={disabled} onClick={() => confirmationHref ? navigate(`/booking/workshops?userVehicleId=${encodeURIComponent(card.vehicle.userVehicleId)}`) : setChanging(true)}>
            Đổi xưởng / thời gian
          </Button>
          {!confirmationHref && <Button
            size="sm"
            variant="ghost"
            loading={working === 'cancel'}
            disabled={disabled}
            onClick={() => run('cancel', () => actions!.cancel(card.proposalId))}
          >
            Hủy đề xuất
          </Button>}
        </div>
      )}

      {view.ticketHref && (
        <Link to={view.ticketHref} className="inline-flex text-xs font-medium text-emerald hover:text-emerald-bright">
          Xem vé lịch hẹn
        </Link>
      )}
      {view.canRetry && actions && (
        <Button size="sm" variant="secondary" disabled={actions.busy} onClick={() => void actions.start()}>
          Tạo đề xuất mới
        </Button>
      )}
      </div>
    </div>
  )
}

/** "Đổi xưởng / thời gian": the offered options, or another day at the selected workshop (API-BK-02). */
function ChangePanel({
  card,
  busy,
  onPick,
  onClose,
}: {
  card: Card
  busy: boolean
  onPick: (choice: { workshopId: string; date: string; timeSlot: string }) => void
  onClose: () => void
}) {
  const options = [card.primary, ...card.alternatives]
  const [selected, setSelected] = useState(options[0].optionId)
  const option = options.find(o => o.optionId === selected) ?? options[0]
  const [day, setDay] = useState<string | null>(null)
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [slot, setSlot] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const now = new Date()
  const today = vnDay(now)
  const lastDay = vnDay(new Date(now.getTime() + HORIZON_DAYS * 86_400_000))

  useEffect(() => {
    if (!day) return
    const controller = new AbortController()
    setSlots(null)
    setSlot(null)
    setLoadError(false)
    getAvailability({ workshopId: option.workshopId, date: day, withAlternatives: false, signal: controller.signal })
      .then(data => {
        const soon = new Date(Date.now() + MIN_LEAD_MS)
        setSlots(data.slots.map(s => (isPastSlot(day, s.timeSlot, soon) ? { ...s, available: false } : s)))
      })
      .catch(error => {
        if (!controller.signal.aborted && isApiError(error)) setLoadError(true)
      })
    return () => controller.abort()
  }, [day, option.workshopId])

  const choice = day && slot ? { workshopId: option.workshopId, date: day, timeSlot: slot } : { workshopId: option.workshopId, date: option.date, timeSlot: option.timeSlot }
  const unchanged = choice.workshopId === card.primary.workshopId && choice.date === card.primary.date && choice.timeSlot === card.primary.timeSlot

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold text-foreground mb-1">Chọn phương án</legend>
        {options.map(o => (
          <label key={o.optionId} className="flex items-start gap-2 text-xs cursor-pointer">
            <input
              type="radio"
              name={`proposal-${card.proposalId}`}
              checked={selected === o.optionId}
              onChange={() => {
                setSelected(o.optionId)
                setDay(null)
              }}
              className="mt-0.5 accent-emerald"
            />
            <span>
              <span className="font-medium text-foreground">{o.workshopName}</span>
              {o.distanceKm !== null && <span className="text-muted"> · {formatDistance(o.distanceKm)}</span>}
              <span className="block text-muted">
                {formatLongDay(o.date)} · {o.timeSlot}
                {o.estimate ? ` · ${formatMoney(o.estimate.chargeableTotal)}` : ''}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="space-y-2">
        <label className="block text-xs font-semibold text-foreground" htmlFor={`day-${card.proposalId}`}>
          Hoặc chọn ngày khác tại {option.workshopName}
        </label>
        <input
          id={`day-${card.proposalId}`}
          type="date"
          min={today}
          max={lastDay}
          value={day ?? ''}
          onChange={event => setDay(event.target.value || null)}
          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground"
        />
        {day && loadError && <p className="text-xs text-error">Không tải được khung giờ. Thử chọn lại ngày.</p>}
        {day && !loadError && slots === null && <p className="text-xs text-muted">Đang tải khung giờ...</p>}
        {day && slots !== null && (slots.length === 0 ? (
          <p className="text-xs text-muted">Xưởng nghỉ ngày này.</p>
        ) : (
          <SlotGrid slots={slots} selected={slot} pending={null} onSelect={s => setSlot(slotLabel(s.timeSlot))} />
        ))}
      </div>

      <div className="flex flex-col min-[400px]:flex-row gap-2">
        <Button size="sm" loading={busy} disabled={busy || unchanged || (day !== null && slot === null)} onClick={() => onPick(choice)}>
          Dùng phương án này
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onClose}>
          Quay lại
        </Button>
      </div>
    </div>
  )
}
