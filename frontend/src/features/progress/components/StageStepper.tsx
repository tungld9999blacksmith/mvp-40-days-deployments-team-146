import { Check, Clock } from 'lucide-react'
import { cn } from '@/shared/ui/cn'
import { formatTimeDayMonth } from '@/shared/utils/format'
import type { Progress, Stage } from '../types'

/** FE §2.0 — stage code ↔ label. */
export const STAGE_LABEL: Record<Stage, string> = {
  CHECKED_IN: 'Đã tiếp nhận',
  INSPECTING: 'Đang kiểm tra',
  SERVICING: 'Đang bảo dưỡng',
  WAITING_PARTS: 'Chờ phụ tùng',
  QUALITY_CHECK: 'Kiểm tra chất lượng',
  READY_FOR_PICKUP: 'Sẵn sàng giao xe',
}

const ORDER: Stage[] = ['CHECKED_IN', 'INSPECTING', 'SERVICING', 'WAITING_PARTS', 'QUALITY_CHECK', 'READY_FOR_PICKUP']

/**
 * FE §2.1 — 6 steps, horizontal on desktop / vertical on mobile. "Chờ phụ tùng" only shows when it
 * happened, so it never looks mandatory. Entries are listed newest first below the stepper.
 */
export default function StageStepper({ progress, showActor }: { progress: Progress; showActor: boolean }) {
  const seen = new Set(progress.entries.map(entry => entry.stage))
  const current = progress.currentStage
  const steps = ORDER.filter(stage => stage !== 'WAITING_PARTS' || seen.has('WAITING_PARTS'))
  const currentIndex = current ? steps.indexOf(current) : -1
  const entries = [...progress.entries].reverse()

  return (
    <div className="space-y-4">
      <ol className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-0" aria-label="Tiến độ dịch vụ">
        {steps.map((stage, index) => {
          const done = index < currentIndex || (progress.isFrozen && progress.bookingStatus === 'COMPLETED')
          const active = index === currentIndex && !(progress.isFrozen && progress.bookingStatus === 'COMPLETED')
          return (
            <li key={stage} className="flex sm:flex-col items-center sm:flex-1 gap-3 sm:gap-2 relative">
              {index < steps.length - 1 && (
                <span
                  aria-hidden
                  className={cn(
                    'hidden sm:block absolute top-3.5 left-1/2 w-full h-0.5',
                    index < currentIndex ? 'bg-emerald' : 'bg-border',
                  )}
                />
              )}
              <span
                aria-current={active ? 'step' : undefined}
                className={cn(
                  'relative z-10 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border shrink-0',
                  done && 'bg-brand border-brand text-on-brand',
                  active && (stage === 'WAITING_PARTS' ? 'bg-warning/15 border-warning text-warning' : 'bg-emerald/15 border-emerald text-emerald ring-4 ring-emerald/15'),
                  !done && !active && 'bg-card border-border text-muted',
                )}
              >
                {done ? <Check className="w-3.5 h-3.5" strokeWidth={2.5} /> : stage === 'WAITING_PARTS' ? <Clock className="w-3.5 h-3.5" /> : index + 1}
              </span>
              <span className={cn('text-xs sm:text-center sm:px-1', active ? 'text-foreground font-semibold' : done ? 'text-foreground' : 'text-muted')}>
                {STAGE_LABEL[stage]}
              </span>
            </li>
          )
        })}
      </ol>

      {entries.length > 0 && (
        <ul className="space-y-2 border-t border-border pt-3">
          {entries.map(entry => (
            <li key={`${entry.stage}-${entry.createdAt}`} className="text-sm flex gap-3">
              <span className="text-xs text-muted font-mono whitespace-nowrap pt-0.5">{formatTimeDayMonth(entry.createdAt)}</span>
              <span className="min-w-0">
                <span className="text-foreground font-medium">{STAGE_LABEL[entry.stage]}</span>
                {showActor && (
                  <span className="text-xs text-muted"> · {entry.actorType === 'SYSTEM' ? 'Hệ thống' : entry.actorName || 'Chủ xưởng'}</span>
                )}
                {entry.note && <span className="block text-muted whitespace-pre-wrap">{entry.note}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
