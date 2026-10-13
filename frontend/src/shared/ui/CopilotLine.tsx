import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { RobotMascot } from './RobotAvatar'
import { cn } from './cn'

/**
 * The assistant on light pages (DESIGN.md "Copilot line"): one thin ink strip, a cyan label, one sentence
 * with the real figure, one ghost action. At most one per page; callers render it only when there is
 * something real to say.
 */
export default function CopilotLine({
  label = 'Trợ lý gợi ý',
  action,
  className,
  children,
}: {
  label?: string
  action: { to: string; label: string }
  className?: string
  children: ReactNode
}) {
  return (
    <aside
      aria-label={label}
      className={cn(
        'flex flex-wrap sm:flex-nowrap items-center gap-3 rounded-2xl border border-banner-border bg-banner text-banner-foreground p-3 pl-3.5',
        className,
      )}
    >
      <span className="relative w-9 h-9 rounded-full border border-banner-border bg-banner-raised flex items-center justify-center shrink-0" aria-hidden>
        <RobotMascot size={28} onInk />
        <span className="absolute -right-0.5 -bottom-0.5 w-2.5 h-2.5 rounded-full bg-assistant-signal ring-2 ring-banner" />
      </span>
      <p className="flex-1 min-w-0 text-sm text-banner-muted">
        <span className="block mb-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-assistant-signal">{label}</span>
        {children}
      </p>
      <Link
        to={action.to}
        className="w-full sm:w-auto inline-flex min-h-9 items-center justify-center rounded-xl border border-banner-border px-3.5 text-sm font-semibold text-banner-foreground hover:border-banner-muted transition-colors shrink-0"
      >
        {action.label}
      </Link>
    </aside>
  )
}
