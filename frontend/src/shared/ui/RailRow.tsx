import type { ReactNode } from 'react'
import { cn } from './cn'

/**
 * One row of a context rail (booking summary, booking preview, service record): icon, small label,
 * value underneath, optional action on the right. Rows are separated by hairlines.
 * `empty` greys the icon and shows the value as a placeholder ("Chưa chọn").
 */
export default function RailRow({
  icon,
  label,
  children,
  action,
  empty,
}: {
  icon: ReactNode
  label: string
  children: ReactNode
  action?: ReactNode
  empty?: boolean
}) {
  return (
    <div className="grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-start gap-x-3 py-3 border-t border-border first:border-t-0 first:pt-0 last:pb-0">
      <span className={cn('mt-0.5 [&>svg]:w-4 [&>svg]:h-4', empty ? 'text-muted' : 'text-emerald')} aria-hidden>
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <div className={cn('text-sm mt-0.5', empty ? 'text-muted italic' : 'font-semibold text-foreground')}>{children}</div>
      </div>
      {action ?? <span />}
    </div>
  )
}
