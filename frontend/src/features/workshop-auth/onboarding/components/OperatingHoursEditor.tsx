import { AlertCircle, Copy } from 'lucide-react'
import Button from '@/shared/ui/Button'
import Switch from '@/shared/ui/Switch'
import { cn } from '@/shared/ui/cn'
import { DAY_LABELS, dayError } from '../../operatingHours'
import type { OperatingHour } from '../../types'

const timeInput =
  'w-full bg-background border rounded-xl px-3 py-2 text-sm font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-emerald/40 disabled:opacity-40'

/** 7 rows (Mon → Sun): open toggle + one open/close window per day (US-009 FE §4.3). */
export default function OperatingHoursEditor({
  value,
  onChange,
  errors,
  disabled,
  firstInvalidRef,
}: {
  value: OperatingHour[]
  onChange: (hours: OperatingHour[]) => void
  errors: Record<string, string>
  disabled?: boolean
  firstInvalidRef?: (element: HTMLInputElement | null, index: number) => void
}) {
  function patch(index: number, change: Partial<OperatingHour>) {
    onChange(value.map((hour, i) => (i === index ? { ...hour, ...change } : hour)))
  }

  function toggle(index: number, open: boolean) {
    const current = value[index]
    patch(
      index,
      open
        ? { isClosed: false, openTime: current.openTime ?? '08:00', closeTime: current.closeTime ?? '17:30' }
        : { isClosed: true, openTime: null, closeTime: null },
    )
  }

  function copyMonday() {
    const monday = value[0]
    onChange(value.map((hour, i) => (i >= 1 && i <= 5 ? { ...monday, dayOfWeek: hour.dayOfWeek } : hour)))
  }

  return (
    <div>
      <div className="hidden sm:grid grid-cols-[7rem_6rem_1fr_1fr] gap-3 px-1 pb-2 text-xs font-medium text-muted">
        <span>Ngày</span>
        <span>Mở cửa</span>
        <span>Giờ mở</span>
        <span>Giờ đóng</span>
      </div>
      <ul className="space-y-2">
        {value.map((hour, index) => {
          const error = dayError(errors, index)
          const day = DAY_LABELS[index]
          return (
            <li key={hour.dayOfWeek} className={cn('rounded-xl border p-3 sm:p-2 sm:px-1 sm:border-0', error ? 'border-error/40' : 'border-border')}>
              <div className="grid grid-cols-2 sm:grid-cols-[7rem_6rem_1fr_1fr] gap-3 items-center">
                <span className="text-sm font-medium text-foreground">{day}</span>
                <span className="flex items-center gap-2 justify-self-end sm:justify-self-start">
                  <Switch
                    size="sm"
                    checked={!hour.isClosed}
                    onChange={open => toggle(index, open)}
                    label={`Mở cửa ${day}`}
                    disabled={disabled}
                  />
                  <span className="text-xs text-muted sm:hidden">{hour.isClosed ? 'Đóng cửa' : 'Mở cửa'}</span>
                </span>
                {hour.isClosed ? (
                  <span className="col-span-2 text-sm text-muted">Đóng cửa</span>
                ) : (
                  <>
                    <input
                      type="time"
                      step={900}
                      aria-label={`Giờ mở cửa ${day}`}
                      aria-invalid={error ? true : undefined}
                      ref={element => firstInvalidRef?.(element, index)}
                      className={cn(timeInput, error ? 'border-error' : 'border-border')}
                      value={hour.openTime ?? ''}
                      disabled={disabled}
                      onChange={e => patch(index, { openTime: e.target.value || null })}
                    />
                    <input
                      type="time"
                      step={900}
                      aria-label={`Giờ đóng cửa ${day}`}
                      aria-invalid={error ? true : undefined}
                      className={cn(timeInput, error ? 'border-error' : 'border-border')}
                      value={hour.closeTime ?? ''}
                      disabled={disabled}
                      onChange={e => patch(index, { closeTime: e.target.value || null })}
                    />
                  </>
                )}
              </div>
              {error && (
                <p className="flex items-center gap-1.5 text-xs text-error mt-2 sm:ml-[13.75rem]">
                  <AlertCircle className="w-3.5 h-3.5" aria-hidden />
                  {error}
                </p>
              )}
            </li>
          )
        })}
      </ul>
      {errors.operatingHours && (
        <p role="alert" className="flex items-center gap-1.5 text-xs text-error mt-3">
          <AlertCircle className="w-3.5 h-3.5" aria-hidden />
          {errors.operatingHours}
        </p>
      )}
      <Button variant="ghost" size="sm" className="mt-3" onClick={copyMonday} disabled={disabled} icon={<Copy className="w-3.5 h-3.5" />}>
        Áp dụng giờ Thứ 2 cho các ngày khác
      </Button>
    </div>
  )
}
