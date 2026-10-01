import { Check } from 'lucide-react'
import { cn } from './cn'

/** Onboarding stepper. Full labels on desktop, "Bước 1/3 · …" on mobile. */
export default function Stepper({ steps, current, completed }: { steps: string[]; current: number; completed: number }) {
  return (
    <nav aria-label="Tiến trình">
      <p className="sm:hidden text-xs text-muted">
        Bước {current + 1}/{steps.length} · <span className="text-foreground font-medium">{steps[current]}</span>
      </p>
      <ol className="hidden sm:flex items-center gap-3">
        {steps.map((label, index) => {
          const done = index < completed && index !== current
          const active = index === current
          return (
            <li key={label} className="flex items-center gap-3 flex-1 last:flex-none">
              <span aria-current={active ? 'step' : undefined} className="flex items-center gap-2.5 whitespace-nowrap">
                <span
                  className={cn(
                    'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border transition-colors',
                    active && 'bg-emerald border-emerald text-background',
                    done && 'bg-emerald/10 border-emerald/30 text-emerald',
                    !active && !done && 'bg-card border-border text-muted',
                  )}
                >
                  {done ? <Check className="w-3.5 h-3.5" strokeWidth={2.5} /> : index + 1}
                </span>
                <span className={cn('text-sm', active ? 'text-foreground font-medium' : 'text-muted')}>{label}</span>
              </span>
              {index < steps.length - 1 && <span aria-hidden className="h-px flex-1 bg-border" />}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
