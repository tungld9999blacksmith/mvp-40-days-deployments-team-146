import { useRef, type KeyboardEvent } from 'react'
import { Star } from 'lucide-react'
import { cn } from '@/shared/ui/cn'

export const RATING_LABELS = ['Rất tệ', 'Chưa tốt', 'Bình thường', 'Tốt', 'Rất tốt']

/**
 * us-041 §4.1 — 1..5 radiogroup, arrow keys move the choice; the selected label is written out so
 * the choice never depends on colour alone. Stars are ≥ 44 px for touch.
 */
export default function StarRating({
  value,
  onChange,
  disabled,
  error,
}: {
  value: number | null
  onChange: (value: number) => void
  disabled?: boolean
  error?: string | null
}) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return
    const current = value ?? 0
    let next: number | null = null
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = Math.min(5, current + 1)
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = Math.max(1, current - 1)
    if (next === null) return
    event.preventDefault()
    onChange(next)
    buttons.current[next - 1]?.focus()
  }

  return (
    <div>
      <div role="radiogroup" aria-label="Mức độ hài lòng" aria-invalid={Boolean(error) || undefined} className="flex gap-1.5" onKeyDown={onKeyDown}>
        {RATING_LABELS.map((label, index) => {
          const rating = index + 1
          const filled = value !== null && rating <= value
          const checked = value === rating
          return (
            <button
              key={label}
              ref={node => {
                buttons.current[index] = node
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-label={`${rating} sao — ${label}`}
              tabIndex={checked || (value === null && rating === 1) ? 0 : -1}
              disabled={disabled}
              onClick={() => onChange(rating)}
              className="w-12 h-12 rounded-xl flex items-center justify-center transition-transform hover:scale-110 disabled:hover:scale-100 focus-visible:ring-4 focus-visible:ring-emerald/25 focus-visible:outline-none"
            >
              <Star className={cn('w-9 h-9 transition-colors', filled ? 'text-warning fill-warning' : 'text-muted/50')} strokeWidth={1.5} />
            </button>
          )
        })}
      </div>
      <p className="text-sm mt-1.5 h-5 text-foreground font-medium">{value ? RATING_LABELS[value - 1] : ''}</p>
      {error && (
        <p role="alert" className="text-xs text-error">
          {error}
        </p>
      )}
    </div>
  )
}
