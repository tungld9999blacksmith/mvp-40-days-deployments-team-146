import { useEffect, useState } from 'react'
import { CalendarClock, Car, FileText, MapPin, RotateCw, Timer, Wrench } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import { TextArea } from '@/shared/ui/Field'
import { cn } from '@/shared/ui/cn'
import { formatCountdown, formatKm, formatLicensePlate } from '@/shared/utils/format'
import type { MilestoneItem, VehicleSummary } from '@/features/vehicles/types'
import { formatLongDay, NOTE_MAX_LENGTH, secondsLeft, slotLabel } from '../utils'

export interface BookingSummaryCardProps {
  workshop: { name: string; address: string | null }
  date: string
  timeSlot: string
  vehicle: VehicleSummary
  odoMilestone: number | null
  items: MilestoneItem[]
  quoteId: string | null
  /** epoch ms; the card is unusable afterwards (FF EF-001). */
  tokenExpiresAt: number
  submitting?: boolean
  note?: string
  onNoteChange?: (note: string) => void
  onConfirm: () => void
  onEdit: () => void
  onCancel: () => void
  onRecheck: () => void
}

/** Workshop name with its address underneath, right-aligned inside an InfoRow. */
export function WorkshopValue({ name, address }: { name: string; address: string | null }) {
  return (
    <span className="flex flex-col items-end">
      <span>{name}</span>
      {address && (
        <span className="inline-flex items-center gap-1 text-xs font-normal text-muted mt-0.5">
          <MapPin className="w-3 h-3 shrink-0" />
          {address}
        </span>
      )}
    </span>
  )
}

function useSecondsLeft(until: number): number {
  const [left, setLeft] = useState(() => secondsLeft(until))
  useEffect(() => {
    setLeft(secondsLeft(until))
    const timer = window.setInterval(() => setLeft(secondsLeft(until)), 1000)
    return () => window.clearInterval(timer)
  }, [until])
  return left
}

/**
 * FE §3.5 / §4.4 — summary shown before the owner confirms. Never creates a booking
 * by itself: only `onConfirm` does (AC-FE-401). Shared with the chat card.
 */
export default function BookingSummaryCard(props: BookingSummaryCardProps) {
  const { workshop, date, timeSlot, vehicle, odoMilestone, items, quoteId, tokenExpiresAt, submitting } = props
  const left = useSecondsLeft(tokenExpiresAt)
  const expired = left <= 0

  return (
    <Card className="space-y-5">
      <div>
        <CardHeader title="Thẻ tóm tắt" icon={<CalendarClock className="w-4 h-4 text-muted" />} />
        <InfoRow label="Xưởng" value={<WorkshopValue name={workshop.name} address={workshop.address} />} />
        <InfoRow label="Thời gian" value={`${slotLabel(timeSlot)} · ${formatLongDay(date)}`} />
        <InfoRow
          label="Xe"
          value={
            <span className="inline-flex items-center gap-1.5">
              <Car className="w-3.5 h-3.5 text-muted" />
              {[vehicle.modelName, vehicle.trim].filter(Boolean).join(' ') || 'Xe của bạn'} · {formatLicensePlate(vehicle.licensePlate)}
            </span>
          }
        />
        {odoMilestone !== null && <InfoRow label="Mốc bảo dưỡng" value={formatKm(odoMilestone)} />}
        <InfoRow
          label="Chi phí"
          value={
            quoteId ? (
              <span className="inline-flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-muted" />
                Theo báo giá đã duyệt
              </span>
            ) : (
              <span className="text-muted">Chưa có ước tính</span>
            )
          }
        />
      </div>

      {items.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2 flex items-center gap-1.5">
            <Wrench className="w-3.5 h-3.5" />
            Hạng mục của mốc
          </p>
          <ul className="space-y-1.5">
            {items.map(item => (
              <li key={item.itemCode} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-foreground">{item.itemName}</span>
                {item.isCoveredByWarranty && <span className="text-xs text-emerald">Bảo hành</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {props.onNoteChange && (
        <TextArea
          label="Ghi chú cho xưởng"
          optional
          rows={3}
          maxLength={NOTE_MAX_LENGTH}
          value={props.note ?? ''}
          onChange={event => props.onNoteChange?.(event.target.value)}
          helper={`${(props.note ?? '').length}/${NOTE_MAX_LENGTH}`}
          disabled={submitting}
        />
      )}

      <div
        className={cn(
          'flex items-center gap-2 text-sm rounded-xl px-3 py-2 border',
          expired ? 'text-error border-error/20 bg-error/10' : left <= 60 ? 'text-warning border-warning/20 bg-warning/10' : 'text-muted border-border',
        )}
        aria-live={left <= 60 ? 'polite' : undefined}
      >
        <Timer className="w-4 h-4 shrink-0" />
        {expired ? 'Thẻ đặt lịch đã hết hiệu lực.' : `Thẻ còn hiệu lực ${formatCountdown(left)}`}
      </div>

      <div className="flex flex-col-reverse sm:flex-row gap-2">
        <Button variant="ghost" onClick={props.onCancel} disabled={submitting}>
          Huỷ
        </Button>
        <Button variant="secondary" onClick={props.onEdit} disabled={submitting}>
          Sửa
        </Button>
        {expired ? (
          <Button className="sm:flex-1" icon={<RotateCw className="w-4 h-4" />} onClick={props.onRecheck}>
            Kiểm tra lại
          </Button>
        ) : (
          <Button className="sm:flex-1" onClick={props.onConfirm} loading={submitting} loadingText="Đang giữ chỗ…">
            Xác nhận
          </Button>
        )}
      </div>
    </Card>
  )
}
