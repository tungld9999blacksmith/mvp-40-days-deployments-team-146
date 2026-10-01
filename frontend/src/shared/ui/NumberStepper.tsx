import type { ReactNode } from 'react'
import { Minus, Plus } from 'lucide-react'
import { Field } from './Field'
import { cn } from './cn'

/** − [ n ] + integer input with an inline label/error (US-021 FE §4.2). */
export default function NumberStepper({
  label,
  value,
  onChange,
  min,
  max,
  unit,
  helper,
  error,
  disabled,
  decreaseLabel = 'Giảm',
  increaseLabel = 'Tăng',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  min: number
  max: number
  unit?: string
  helper?: ReactNode
  error?: string
  disabled?: boolean
  decreaseLabel?: string
  increaseLabel?: string
}) {
  const numeric = Number(value)
  const valid = value.trim() !== '' && Number.isInteger(numeric)
  const step = (delta: number) => {
    const base = valid ? numeric : min
    onChange(String(Math.min(max, Math.max(min, base + delta))))
  }
  const button =
    'w-10 h-10 flex-shrink-0 rounded-xl bg-card border border-border flex items-center justify-center text-muted hover:text-foreground hover:bg-card-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed'

  return (
    <Field label={label} error={error} helper={helper}>
      {({ inputId, describedBy, invalid }) => (
        <div className="flex items-center gap-2">
          <button type="button" className={button} onClick={() => step(-1)} disabled={disabled || (valid && numeric <= min)} aria-label={decreaseLabel}>
            <Minus className="w-4 h-4" />
          </button>
          <input
            id={inputId}
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            step={1}
            value={value}
            disabled={disabled}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            onChange={e => onChange(e.target.value.replace(/[^\d]/g, ''))}
            className={cn(
              'w-20 text-center bg-card border rounded-xl px-3 py-2.5 text-sm font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-emerald/40 disabled:opacity-60',
              invalid ? 'border-error' : 'border-border',
            )}
          />
          <button type="button" className={button} onClick={() => step(1)} disabled={disabled || (valid && numeric >= max)} aria-label={increaseLabel}>
            <Plus className="w-4 h-4" />
          </button>
          {unit && <span className="text-sm text-muted ml-1">{unit}</span>}
        </div>
      )}
    </Field>
  )
}
