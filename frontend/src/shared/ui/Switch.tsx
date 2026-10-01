import { cn } from './cn'

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
  describedBy?: string
  size?: 'sm' | 'md'
}

export default function Switch({ checked, onChange, label, disabled, describedBy, size = 'md' }: SwitchProps) {
  const track = size === 'sm' ? 'w-8 h-5' : 'w-11 h-6'
  const knob = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4.5 h-4.5'
  const shift = size === 'sm' ? 'translate-x-3.5' : 'translate-x-5'
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex flex-shrink-0 items-center rounded-full border transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald/50 disabled:opacity-50 disabled:cursor-not-allowed',
        track,
        checked ? 'bg-emerald border-emerald' : 'bg-card border-border',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'ml-0.5 rounded-full transition-transform duration-150',
          knob,
          checked ? cn('bg-background', shift) : 'bg-muted translate-x-0',
        )}
      />
    </button>
  )
}
