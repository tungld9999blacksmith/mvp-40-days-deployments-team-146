import { Loader2 } from 'lucide-react'
import { cn } from './cn'

export default function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <Loader2
      className={cn('animate-spin', className ?? 'w-4 h-4')}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'status' : undefined}
    />
  )
}
