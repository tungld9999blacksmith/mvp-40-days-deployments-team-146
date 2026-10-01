import { cn } from '@/shared/ui/cn'
import type { Slot } from '../types'
import { dayChip, remainingLabel, slotLabel } from '../utils'

/** `past` = every slot of today already started; `closed` = workshop does not open. */
export type DayState = 'loading' | 'open' | 'full' | 'past' | 'closed' | 'error'

/** FE §3.4 — 7-day strip; closed days are disabled with "Nghỉ". */
export function DayStrip({
  days,
  states,
  selected,
  onSelect,
}: {
  days: string[]
  states: Record<string, DayState>
  selected: string | null
  onSelect: (day: string) => void
}) {
  return (
    <div role="radiogroup" aria-label="Ngày" className="grid grid-cols-4 sm:grid-cols-7 gap-2">
      {days.map(day => {
        const chip = dayChip(day)
        const state = states[day] ?? 'loading'
        const disabled = state === 'closed' || state === 'past'
        const active = selected === day
        return (
          <button
            key={day}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onSelect(day)}
            className={cn(
              'rounded-xl border px-2 py-2.5 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/40',
              active ? 'border-emerald bg-emerald/10' : 'border-border bg-card hover:bg-card-hover',
              disabled && 'opacity-50 cursor-not-allowed hover:bg-card',
            )}
          >
            <span className={cn('block text-xs', active ? 'text-emerald' : 'text-muted')}>{chip.weekday}</span>
            <span className={cn('block text-sm font-semibold', active ? 'text-emerald' : 'text-foreground')}>
              {chip.dayMonth}
            </span>
            <span className="block text-[11px] mt-0.5 h-4 text-muted">
              {state === 'closed' ? 'Nghỉ' : state === 'past' ? 'Hết giờ' : state === 'full' ? 'Kín lịch' : ''}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/** FE §4.3 — slots of the chosen day; full slots stay visible with the text "Hết chỗ". */
export function SlotGrid({
  slots,
  selected,
  pending,
  onSelect,
}: {
  slots: Slot[]
  selected: string | null
  /** Slot whose token is being requested. */
  pending: string | null
  onSelect: (slot: Slot) => void
}) {
  return (
    <div role="radiogroup" aria-label="Khung giờ" className="grid grid-cols-3 lg:grid-cols-6 gap-2">
      {slots.map(slot => {
        const label = slotLabel(slot.timeSlot)
        const note = remainingLabel(slot.remaining, slot.available)
        const active = selected === label
        const disabled = !slot.available || pending !== null
        return (
          <button
            key={slot.timeSlot}
            type="button"
            role="radio"
            aria-checked={active}
            aria-busy={pending === label || undefined}
            disabled={disabled}
            onClick={() => onSelect(slot)}
            className={cn(
              'rounded-xl border px-2 py-3 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/40',
              active ? 'border-emerald bg-emerald/10' : 'border-border bg-card hover:bg-card-hover',
              !slot.available && 'opacity-50 cursor-not-allowed hover:bg-card',
              pending === label && 'animate-pulse',
            )}
          >
            <span className={cn('block text-sm font-semibold', active ? 'text-emerald' : 'text-foreground')}>{label}</span>
            <span className={cn('block text-[11px] mt-0.5 h-4', slot.available ? 'text-warning' : 'text-error')}>{note ?? ''}</span>
          </button>
        )
      })}
    </div>
  )
}
