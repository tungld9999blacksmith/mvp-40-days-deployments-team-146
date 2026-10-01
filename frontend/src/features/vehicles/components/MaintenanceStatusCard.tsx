import { Link } from 'react-router-dom'
import { Bot, CalendarClock, ChevronRight, ShieldCheck, Wrench } from 'lucide-react'
import type { ApiError } from '@/shared/api/client'
import { Card, CardHeader } from '@/shared/ui/Card'
import Button from '@/shared/ui/Button'
import Skeleton from '@/shared/ui/Skeleton'
import Spinner from '@/shared/ui/Spinner'
import { ErrorState, Notice } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { formatDate, formatKm, formatTimeDayMonth } from '@/shared/utils/format'
import type { MaintenanceStatus } from '../types'
import { DUE_REASON_TEXT, milestoneProgress, milestoneTitle, remainingParts } from '../utils/maintenanceFormat'
import DueStatusBadge, { dueTone } from './DueStatusBadge'

const TONE_TEXT = { success: 'text-emerald', warning: 'text-warning', error: 'text-error', neutral: 'text-muted' }
const TONE_BAR = { success: 'bg-emerald', warning: 'bg-warning', error: 'bg-error', neutral: 'bg-muted' }

export const ASK_AI_QUESTION = 'Mốc bảo dưỡng tới của xe tôi cần làm gì?'

interface Props {
  status: MaintenanceStatus | null
  error: ApiError | null
  onRetry: () => void
  retrying?: boolean
  variant: 'compact' | 'full'
  pendingSyncExhausted?: boolean
  onRetryPendingSync?: () => void
}

/** Due status card — shows backend values only, never computes them (BR-008, US-017 FE §4.2). */
export default function MaintenanceStatusCard({
  status,
  error,
  onRetry,
  retrying,
  variant,
  pendingSyncExhausted,
  onRetryPendingSync,
}: Props) {
  const compact = variant === 'compact'

  if (!status) {
    return (
      <Card className="h-full">
        <CardHeader title="Bảo dưỡng" icon={<Wrench className="w-4 h-4 text-muted" />} />
        {error ? (
          <ErrorState compact title="Không tải được trạng thái bảo dưỡng." description={null} traceId={error.traceId} onRetry={onRetry} retrying={retrying} />
        ) : (
          <div className="space-y-3" aria-busy="true">
            <Skeleton className="h-6 w-28 rounded-full" />
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-2 w-full" />
          </div>
        )}
      </Card>
    )
  }

  const tone = dueTone(status.dueStatus)
  const unknown = status.dueStatus === 'UNKNOWN' || !['NORMAL', 'DUE_SOON', 'OVERDUE'].includes(status.dueStatus)
  const parts = unknown ? [] : remainingParts(status)
  const progress = unknown ? null : milestoneProgress(status)
  const alerting = status.dueStatus === 'DUE_SOON' || status.dueStatus === 'OVERDUE'
  const items = status.nextMilestone?.items ?? []
  const shownItems = compact ? items.slice(0, 3) : items

  return (
    <Card className="h-full flex flex-col">
      <CardHeader
        title="Bảo dưỡng"
        action={
          <span className="flex items-center gap-2">
            {retrying && <Spinner className="w-3.5 h-3.5 text-muted" label="Đang cập nhật" />}
            <DueStatusBadge status={status.dueStatus} />
          </span>
        }
      />

      {status.unknownReason === 'OEM_DATA_NOT_SYNCED' ? (
        <div aria-live="polite">
          {pendingSyncExhausted ? (
            <Notice
              tone="info"
              action={
                <Button variant="secondary" size="sm" onClick={onRetryPendingSync}>
                  Tải lại
                </Button>
              }
            >
              Hãng chưa gửi dữ liệu. Vui lòng quay lại sau ít phút.
            </Notice>
          ) : (
            <Notice icon={<Spinner className="w-4 h-4 text-muted" />}>Đang lấy dữ liệu từ hãng...</Notice>
          )}
        </div>
      ) : status.unknownReason === 'NO_MAINTENANCE_RULE' || unknown ? (
        <Notice>Chưa có lịch bảo dưỡng cho mẫu xe này — vui lòng liên hệ xưởng.</Notice>
      ) : (
        <>
          <div className={cn('flex flex-wrap items-baseline gap-x-1.5', compact ? 'text-xl' : 'text-2xl', 'font-extrabold font-mono')}>
            {parts.map((part, index) => (
              <span key={part.kind} className={part.emphasized ? TONE_TEXT[tone] : alerting ? 'text-muted' : 'text-foreground'}>
                {index > 0 && <span className="text-muted font-normal mr-1.5">·</span>}
                {part.text}
              </span>
            ))}
          </div>

          {status.nextMilestone && (
            <p className="text-sm text-foreground mt-2">
              {milestoneTitle(status.nextMilestone)}
              {status.nextMilestone.isRecurring && <span className="text-muted"> (mốc định kỳ)</span>}
              <span className="text-muted"> · Đến hạn {formatDate(status.nextMilestone.dueDate)}</span>
            </p>
          )}
          {alerting && status.dueReason && <p className="text-xs text-muted mt-1">{DUE_REASON_TEXT[status.dueReason]}</p>}

          {progress !== null && status.odometer && status.nextMilestone && (
            <div className="mt-4">
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(progress * 100)}
                aria-label={`Tiến độ tới mốc ${formatKm(status.nextMilestone.odoMilestoneKm)}`}
                className="w-full h-1.5 bg-background rounded-full overflow-hidden"
              >
                <div className={cn('h-full rounded-full', TONE_BAR[tone])} style={{ width: `${progress * 100}%` }} />
              </div>
              <div className="flex justify-between mt-1.5 text-xs text-muted font-mono">
                <span>{formatKm(status.odometer.odoKm)}</span>
                <span>{formatKm(status.nextMilestone.odoMilestoneKm)}</span>
              </div>
            </div>
          )}
        </>
      )}

      {status.odometer ? (
        <p className="text-xs text-muted mt-4">
          ODO <span className="font-mono text-foreground">{formatKm(status.odometer.odoKm)}</span> · Hãng cập nhật lúc{' '}
          <span className="font-mono">{formatTimeDayMonth(status.odometer.recordedAt)}</span>
        </p>
      ) : null}

      {status.calculationBasis === 'TIME_ONLY' && (
        <Notice className="mt-3">Hãng chưa có dữ liệu số km — trạng thái tính theo thời gian.</Notice>
      )}
      {status.odometer?.isStale && (
        <Notice tone="warning" className="mt-3">
          Số km được hãng cập nhật lần cuối ngày {formatDate(status.odometer.recordedAt)}, có thể chưa phản ánh hiện tại.
        </Notice>
      )}

      {shownItems.length > 0 && !unknown && (
        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Hạng mục của mốc</p>
          <ul className="space-y-1.5">
            {shownItems.map(item => (
              <li key={item.itemCode} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-foreground">{item.itemName}</span>
                {item.isCoveredByWarranty && (
                  <span className="flex items-center gap-1 text-xs text-emerald whitespace-nowrap">
                    <ShieldCheck className="w-3.5 h-3.5" aria-hidden />
                    Trong bảo hành
                  </span>
                )}
              </li>
            ))}
          </ul>
          {compact && items.length > 3 && <p className="text-xs text-muted mt-2">và {items.length - 3} hạng mục khác</p>}
        </div>
      )}

      <div className="mt-auto pt-5 flex flex-col sm:flex-row gap-2">
        {alerting ? (
          <>
            <Link
              to="/booking"
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm bg-emerald text-background font-semibold hover:bg-emerald-bright transition-colors"
            >
              <CalendarClock className="w-4 h-4" aria-hidden />
              Đặt lịch bảo dưỡng
            </Link>
            <Link
              to={`/ai?q=${encodeURIComponent(ASK_AI_QUESTION)}`}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm bg-card border border-border text-muted hover:text-foreground hover:bg-card-hover transition-colors"
            >
              <Bot className="w-4 h-4" aria-hidden />
              Hỏi AI về mốc này
            </Link>
          </>
        ) : (
          compact &&
          status.dueStatus === 'NORMAL' && (
            <Link to="/vehicle" className="inline-flex items-center gap-1 text-sm text-emerald hover:text-emerald-bright transition-colors">
              Xem chi tiết <ChevronRight className="w-3.5 h-3.5" aria-hidden />
            </Link>
          )
        )}
      </div>
    </Card>
  )
}
