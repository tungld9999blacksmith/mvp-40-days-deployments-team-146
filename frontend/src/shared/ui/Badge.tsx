import type { ReactNode } from 'react'
import { cn } from './cn'

export type BadgeTone = 'success' | 'warning' | 'error' | 'neutral'

const tones: Record<BadgeTone, string> = {
  success: 'text-emerald bg-emerald/10',
  warning: 'text-warning bg-warning/10',
  error: 'text-error bg-error/10',
  neutral: 'text-muted bg-card-hover',
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
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold font-mono uppercase tracking-wide whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}
