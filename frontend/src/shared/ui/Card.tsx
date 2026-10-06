import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from './cn'

// cn() does not resolve Tailwind conflicts and `p-0` sorts before `p-5`, so a caller's
// padding only wins if the default is left out.
const OWN_PADDING = /(^|\s)p-\d/

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  const padded = !OWN_PADDING.test(className ?? '')
  return <div className={cn('bg-card border border-border rounded-2xl elevation-sm', padded && 'p-5', className)} {...rest} />
}

/** Small uppercase section label with an optional outline icon on the right. */
export function CardHeader({ title, icon, action }: { title: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <span className="text-[13px] font-semibold text-muted">{title}</span>
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
