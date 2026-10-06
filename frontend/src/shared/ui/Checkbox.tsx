import { useId, type ReactNode } from 'react'
import { Check, AlertCircle } from 'lucide-react'
import { cn } from './cn'

interface CheckboxProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
  error?: string
  className?: string
}

export default function Checkbox({ checked, onChange, label, description, disabled, error, className }: CheckboxProps) {
  const id = useId()
  const errorId = `${id}-error`
  return (
    <div className={className}>
      <label
        htmlFor={id}
        className={cn('flex items-start gap-3 min-h-11 py-1 select-none', disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer')}
      >
        <input
          id={id}
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          disabled={disabled}
          onChange={e => onChange(e.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
        />
        <span
          aria-hidden
          className={cn(
            'w-5 h-5 flex-shrink-0 rounded-md flex items-center justify-center border transition-colors',
            'peer-focus-visible:ring-2 peer-focus-visible:ring-emerald/50',
            checked ? 'bg-emerald border-emerald' : error ? 'bg-card border-error' : 'bg-card border-border',
          )}
        >
          {checked && <Check className="w-3.5 h-3.5 text-background" strokeWidth={3} />}
        </span>
        <span className="text-sm text-foreground leading-snug">
          {label}
          {description && <span className="block text-xs text-muted mt-0.5">{description}</span>}
        </span>
      </label>
      {error && (
        <p id={errorId} className="flex items-start gap-1.5 text-xs text-error mt-1.5 ml-8">
          <AlertCircle className="w-3.5 h-3.5 mt-px flex-shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  )
}
