import { forwardRef, useState } from 'react'
import { formatNumber } from '@/shared/utils/format'
import { cn } from './cn'

export const MAX_MONEY_DIGITS = 9

/**
 * Digits to keep after an edit of the field (`raw` is the input's new text). An edit
 * that would exceed the limit is refused, never cut: cutting turned a price typed after
 * the prefilled one into a different, valid-looking amount.
 */
export function nextMoneyDigits(previous: string, raw: string): string {
  const digits = raw.replace(/[^\d]/g, '')
  return digits.length > MAX_MONEY_DIGITS ? previous : digits
}

/**
 * VND amount input (digits only, shown with thousand separators when not focused).
 * Focusing selects the whole amount, so typing replaces a prefilled suggestion.
 */
const MoneyInput = forwardRef<
  HTMLInputElement,
  {
    value: string
    onChange: (digits: string) => void
    ariaLabel: string
    placeholder?: number
    invalid?: boolean
    disabled?: boolean
    describedBy?: string
    className?: string
  }
>(function MoneyInput({ value, onChange, ariaLabel, placeholder, invalid, disabled, describedBy, className }, ref) {
  const [focused, setFocused] = useState(false)
  const shown = focused || !value ? value : formatNumber(Number(value))
  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        ref={ref}
        inputMode="numeric"
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        placeholder={placeholder !== undefined ? formatNumber(placeholder) : undefined}
        value={shown}
        disabled={disabled}
        onFocus={event => {
          setFocused(true)
          // After the re-render swaps "200.000" for "200000", which moves the caret to the end.
          const input = event.currentTarget
          requestAnimationFrame(() => {
            if (document.activeElement === input) input.select()
          })
        }}
        onBlur={() => setFocused(false)}
        onChange={event => onChange(nextMoneyDigits(value, event.target.value))}
        className={cn(
          'w-32 bg-card border rounded-lg px-3 py-1.5 text-sm text-right font-mono text-foreground placeholder:text-muted/70 focus:outline-none focus:border-emerald/60 focus:ring-4 focus:ring-emerald/15 disabled:opacity-60',
          invalid ? 'border-error' : 'border-border',
          className,
        )}
      />
      <span className="text-xs text-muted" aria-hidden>
        ₫
      </span>
    </span>
  )
})

export default MoneyInput
