import type { ReactNode } from 'react'
import { cn } from './cn'

export type BadgeTone = 'success' | 'warning' | 'error' | 'neutral'

const tones: Record<BadgeTone, string> = {
  success: 'text-emerald bg-emerald/10 ring-emerald/20',
  warning: 'text-warning bg-warning/10 ring-warning/20',
  error: 'text-error bg-error/10 ring-error/20',
  neutral: 'text-muted bg-foreground/5 ring-foreground/10',
}

/** Status badge: always carries text, never color alone. */
export default function Badge({
  tone,
  children,
  icon,
  className,
}: {
  tone: BadgeTone
  children: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ring-1 ring-inset whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon ?? <span aria-hidden className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}
