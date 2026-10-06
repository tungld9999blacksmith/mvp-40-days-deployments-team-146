import { useEffect, useState } from 'react'
import { BadgeCheck, Hand } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { cn } from '@/shared/ui/cn'
import { track } from '@/shared/utils/track'
import { getBookingSettings, saveBookingSettings } from '../api'
import type { BookingSettings } from '../types'

/** SCR-805 — confirmation mode AUTO / MANUAL (API-WB-07 / WB-08); applies to the next bookings. */
export default function BookingSettingsPage() {
  const toast = useToast()
  const [settings, setSettings] = useState<BookingSettings | null>(null)
  const [mode, setMode] = useState<'AUTO' | 'MANUAL'>('MANUAL')
  const [error, setError] = useState<ApiError | null>(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    setError(null)
    getBookingSettings()
      .then(data => {
        setSettings(data)
        setMode(data.confirmationMode)
      })
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }
  useEffect(load, [])

  async function save() {
    setSaving(true)
    try {
      const result = await saveBookingSettings(mode)
      setSettings(result)
      track('confirmation_mode_changed', { mode })
      toast.show('Đã lưu cài đặt đặt lịch.', 'success')
      if (mode === 'AUTO' && result.pendingCount > 0) {
        toast.show(`Còn ${result.pendingCount} yêu cầu đang chờ — vẫn cần bạn xử lý trên Board.`, 'warning')
      }
    } catch (reason) {
      toast.show(isApiError(reason, 'WORKSHOP_INACTIVE') ? 'Xưởng đang tạm ngưng — không lưu được.' : 'Tạm thời chưa lưu được, thử lại nhé.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const options = [
    { value: 'AUTO' as const, title: 'Tự động xác nhận', text: 'Khách giữ chỗ là lịch hẹn được xác nhận ngay.', icon: BadgeCheck },
    {
      value: 'MANUAL' as const,
      title: 'Tôi xác nhận thủ công',
      text: `Bạn cần chấp nhận trong ${settings?.wsConfirmDeadlineHours ?? 12} giờ, nếu không yêu cầu sẽ tự huỷ.`,
      icon: Hand,
    },
  ]

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Cài đặt đặt lịch</h1>
        <p className="text-muted mt-1">Chế độ xác nhận áp dụng cho các lần giữ chỗ sau khi lưu.</p>
      </div>
      {error ? (
        <Card>
          <ErrorState traceId={error.traceId} onRetry={load} />
        </Card>
      ) : !settings ? (
        <Card aria-busy>
          <Skeleton className="h-28 w-full" />
        </Card>
      ) : (
        <Card className="space-y-4">
          <div role="radiogroup" aria-label="Chế độ xác nhận" className="space-y-3">
            {options.map(({ value, title, text, icon: Icon }) => (
              <label
                key={value}
                className={cn(
                  'flex items-start gap-3 rounded-2xl border p-4 cursor-pointer transition-colors',
                  mode === value ? 'border-emerald/50 bg-emerald/5' : 'border-border hover:bg-card-hover',
                )}
              >
                <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="mt-1 accent-emerald" />
                <Icon className={cn('w-5 h-5 mt-0.5 shrink-0', mode === value ? 'text-emerald' : 'text-muted')} />
                <span>
                  <span className="block text-sm font-semibold text-foreground">{title}</span>
                  <span className="block text-sm text-muted mt-0.5">{text}</span>
                </span>
              </label>
            ))}
          </div>
          {settings.pendingCount > 0 && <p className="text-xs text-muted">Đang có {settings.pendingCount} yêu cầu chờ xác nhận trên Board.</p>}
          <div className="flex justify-end">
            <Button loading={saving} loadingText="Đang lưu…" disabled={mode === settings.confirmationMode} onClick={() => void save()}>
              Lưu
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
