import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('bg-card border border-border rounded-2xl p-5', className)} {...rest} />
}

/** Small uppercase section label with an optional outline icon on the right. */
export function CardHeader({ title, icon, action }: { title: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <span className="text-xs font-semibold uppercase tracking-widest text-muted">{title}</span>
      {action ?? icon}
    </div>
  )
}

/** Label / value row used in detail cards. */
export function InfoRow({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-border last:border-b-0">
      <span className="text-sm text-muted">{label}</span>
      <span className={cn('text-sm font-medium text-foreground text-right', mono && 'font-mono')}>{value}</span>
    </div>
  )
}
