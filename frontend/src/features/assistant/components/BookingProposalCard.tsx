import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarClock, Car, MapPin, Wrench } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { cn } from '@/shared/ui/cn'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { getAvailability } from '@/features/bookings/api'
import { SlotGrid } from '@/features/bookings/components/SlotPicker'
import type { Slot } from '@/features/bookings/types'
import { formatLongDay, isPastSlot, slotLabel } from '@/features/bookings/utils'
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
    <div className="mt-3 rounded-xl border border-emerald/25 bg-background/40 p-3.5 space-y-3" aria-label="Đề xuất đặt lịch">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-semibold text-muted flex items-center gap-1.5">
          <CalendarClock className="w-3.5 h-3.5 text-emerald" aria-hidden /> Đề xuất đặt lịch
        </p>
        <Badge tone={view.badge.tone}>{view.badge.label}</Badge>
      </div>

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

      <div className={cn('rounded-lg border border-border p-3 space-y-1', view.status !== 'PROPOSED' && view.status !== 'CONFIRMED' && 'opacity-60')}>
        <OptionLine option={primary} locationLabel={card.locationLabel} />
        <p className="text-sm text-foreground font-medium ml-5">
          {formatLongDay(primary.date)} · <span className="font-mono">{primary.timeSlot}</span>
        </p>
        {primary.estimate && (
          <p className="text-xs ml-5">
            <span className="text-muted">Chi phí ước tính: </span>
            <span className="font-mono font-semibold text-foreground">{formatMoney(primary.estimate.chargeableTotal)}</span>
            {primary.estimate.hasReferencePrice && <span className="text-muted"> · Giá tham khảo, xưởng có thể báo khác</span>}
          </p>
        )}
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
          <Button size="sm" variant="secondary" disabled={disabled} onClick={() => confirmationHref ? navigate('/booking/workshops') : setChanging(true)}>
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
