import { useState } from 'react'
import { ChevronDown, History } from 'lucide-react'
import { cn } from '@/shared/ui/cn'
import { REASON_LABEL } from '@/shared/domain/bookingLabels'
import { formatTimeDayMonth } from '@/shared/utils/format'
import type { BookingHistoryEntry } from '../types'
import { dayChip, slotLabel } from '../utils'

function slotText(slot: { date: string; timeSlot: string }): string {
  return `${dayChip(slot.date).dayMonth} ${slotLabel(slot.timeSlot)}`
}

function entryText(entry: BookingHistoryEntry): string {
  if (entry.kind === 'RESCHEDULE') {
    const from = entry.source === 'REMINDER_24H' ? ' (từ lời nhắc)' : entry.source === 'CHAT' ? ' (qua trò chuyện)' : ''
    return `Đổi giờ ${slotText(entry.from)} → ${slotText(entry.to)}${from}`
  }
  const reason = entry.reasonCode ? REASON_LABEL[entry.reasonCode] ?? entry.reasonCode : null
  switch (entry.toStatus) {
    case 'PENDING':
      return 'Bạn đã giữ chỗ'
    case 'CONFIRMED':
      return entry.actorType === 'SYSTEM' ? 'Hệ thống tự xác nhận' : 'Xưởng chấp nhận'
    case 'CHECKED_IN':
      return 'Xe đã check-in tại xưởng'
    case 'IN_PROGRESS':
      return 'Xưởng bắt đầu làm'
    case 'COMPLETED':
      return 'Hoàn tất dịch vụ'
    case 'CANCELLED':
      if (entry.actorType === 'VEHICLE_OWNER') {
        return entry.reasonCode === 'HOLD_CANCELLED' ? 'Bạn đã huỷ giữ chỗ' : `Bạn đã huỷ lịch${entry.source === 'REMINDER_24H' ? ' (từ lời nhắc)' : ''}`
      }
      if (entry.actorType === 'SYSTEM') return 'Tự huỷ — xưởng chưa xác nhận kịp'
      return entry.fromStatus === 'PENDING' ? `Xưởng chưa nhận lịch${reason ? ` — ${reason}` : ''}` : `Xưởng huỷ lịch${reason ? ` — ${reason}` : ''}`
    default:
      return entry.toStatus
  }
}

/** us-053 §4.4 — status events and reschedules, newest first (BR-1211). */
export default function HistoryTimeline({ history }: { history: BookingHistoryEntry[] }) {
  const [open, setOpen] = useState(false)
  if (history.length === 0) return null
  return (
    <section className="bg-card border border-border rounded-2xl elevation-sm">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3.5 text-sm font-medium text-foreground"
      >
        <span className="inline-flex items-center gap-2">
          <History className="w-4 h-4 text-muted" /> Lịch sử
        </span>
        <ChevronDown className={cn('w-4 h-4 text-muted transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <ol className="px-5 pb-4 space-y-3 border-t border-border pt-3">
          {history.map(entry => (
            <li key={`${entry.kind}-${entry.at}`} className="flex gap-3 text-sm">
              <span className="w-2 h-2 rounded-full bg-emerald/60 mt-1.5 shrink-0" aria-hidden />
              <span className="flex-1 min-w-0">
                <span className="text-foreground">{entryText(entry)}</span>
                {entry.kind === 'STATUS' && entry.note && <span className="block text-muted">"{entry.note}"</span>}
                <span className="block text-xs text-muted font-mono mt-0.5">{formatTimeDayMonth(entry.at)}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
