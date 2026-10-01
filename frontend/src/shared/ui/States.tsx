import type { ReactNode } from 'react'
import { AlertCircle, AlertTriangle, Info, CheckCircle2, RotateCw } from 'lucide-react'
import Button from './Button'
import { cn } from './cn'

/** Empty state: icon + title + description + optional CTA. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center text-center px-6 py-10', className)}>
      {icon && (
        <div className="w-12 h-12 rounded-2xl bg-card-hover border border-border flex items-center justify-center text-muted mb-4">
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {description && <p className="text-sm text-muted mt-1.5 max-w-sm">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/** Error state with retry and the trace id for support. */
export function ErrorState({
  title = 'Không thể tải dữ liệu.',
  description = 'Vui lòng thử lại.',
  traceId,
  onRetry,
  retrying,
  className,
  compact,
}: {
  title?: string
  description?: ReactNode
  traceId?: string | null
  onRetry?: () => void
  retrying?: boolean
  className?: string
  compact?: boolean
}) {
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center text-center', compact ? 'px-4 py-6' : 'px-6 py-10', className)}
    >
      <AlertCircle className="w-6 h-6 text-error mb-3" aria-hidden />
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {description && <p className="text-sm text-muted mt-1">{description}</p>}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry} loading={retrying} icon={<RotateCw className="w-3.5 h-3.5" />}>
          Thử lại
        </Button>
      )}
      {traceId && <p className="text-xs text-muted font-mono mt-3">Mã lỗi: {traceId}</p>}
    </div>
  )
}

type NoticeTone = 'info' | 'warning' | 'error' | 'success'
const noticeStyles: Record<NoticeTone, { box: string; icon: string; Icon: typeof Info }> = {
  info: { box: 'bg-card border-border', icon: 'text-muted', Icon: Info },
  warning: { box: 'bg-warning/10 border-warning/20', icon: 'text-warning', Icon: AlertTriangle },
  error: { box: 'bg-error/10 border-error/20', icon: 'text-error', Icon: AlertCircle },
  success: { box: 'bg-emerald/10 border-emerald/20', icon: 'text-emerald', Icon: CheckCircle2 },
}

/** Inline banner for notices (session expired, stale data, pending sync...). */
export function Notice({
  tone = 'info',
  title,
  children,
  icon,
  action,
  className,
  role,
}: {
  tone?: NoticeTone
  title?: ReactNode
  children?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  className?: string
  role?: 'alert' | 'status'
}) {
  const style = noticeStyles[tone]
  const Icon = style.Icon
  return (
    <div role={role} className={cn('flex items-start gap-3 rounded-xl border px-4 py-3', style.box, className)}>
      <span className={cn('mt-0.5 flex-shrink-0', style.icon)} aria-hidden>
        {icon ?? <Icon className="w-4 h-4" />}
      </span>
      <div className="flex-1 min-w-0 text-sm">
        {title && <p className="font-medium text-foreground">{title}</p>}
        {children && <div className={cn('text-muted', title ? 'mt-0.5' : null)}>{children}</div>}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  )
}
