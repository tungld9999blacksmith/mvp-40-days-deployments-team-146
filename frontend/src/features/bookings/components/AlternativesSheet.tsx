import { ChevronRight } from 'lucide-react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import type { Alternative } from '../types'
import { formatLongDay, remainingLabel, slotLabel } from '../utils'

/** FE §4.5 — at most 3 alternatives when the slot is full (FF BR-008, AC-FE-402). */
export default function AlternativesSheet({
  open,
  alternatives,
  onPick,
  onClose,
}: {
  open: boolean
  alternatives: Alternative[]
  onPick: (alternative: Alternative) => void
  onClose: () => void
}) {
  const options = alternatives.slice(0, 3)
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Khung giờ này đã hết chỗ"
      description={options.length ? 'Bạn có thể chọn một phương án gần nhất dưới đây.' : 'Hiện chưa có phương án thay thế, bạn chọn ngày hoặc xưởng khác nhé.'}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Chọn lại
        </Button>
      }
    >
      {options.length > 0 && (
        <ul className="space-y-2">
          {options.map(alternative => (
            <li key={`${alternative.workshopId}-${alternative.date}-${alternative.timeSlot}`}>
              <button
                type="button"
                onClick={() => onPick(alternative)}
                className="w-full text-left rounded-xl border border-border bg-card px-4 py-3 flex items-center gap-3 hover:bg-card-hover hover:border-emerald/40 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/40"
              >
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-semibold text-foreground truncate">{alternative.name}</span>
                  <span className="block text-xs text-muted mt-0.5">
                    {formatLongDay(alternative.date)} · {slotLabel(alternative.timeSlot)}
                    {remainingLabel(alternative.remaining, true) ? ` · ${remainingLabel(alternative.remaining, true)}` : ''}
                  </span>
                </span>
                <ChevronRight className="w-4 h-4 text-muted shrink-0" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  )
}
