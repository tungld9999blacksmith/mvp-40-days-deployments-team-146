import { cn } from './cn'

export default function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('bg-card-hover rounded-xl animate-pulse', className)} />
}

/** Card-shaped placeholder keeping the final layout size. */
export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('bg-card border border-border rounded-2xl p-5 space-y-3 elevation-sm', className)} aria-busy="true">
      <Skeleton className="h-3 w-24" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn('h-4', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}
