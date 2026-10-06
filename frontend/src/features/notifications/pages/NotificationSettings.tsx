import { useEffect, useId, useRef, useState } from 'react'
import { Link, useBlocker, useLocation } from 'react-router-dom'
import { ArrowLeft, BellRing, Info } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import { setQueryData } from '@/shared/hooks/useCachedQuery'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import NumberStepper from '@/shared/ui/NumberStepper'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import Switch from '@/shared/ui/Switch'
import { cn } from '@/shared/ui/cn'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { useOnboardingRequiredRedirect } from '@/features/auth/hooks/useOnboardingRequiredRedirect'
import { NOTIFICATION_SETTINGS_KEY, updateNotificationSettings } from '../api'
import NotificationChannelList from '../components/NotificationChannelList'
import { useNotificationSettings } from '../hooks/useNotificationSettings'
import { buildSettingsPatch, isDirty, toForm, validateSettings, type SettingsErrors } from '../settingsForm'
import type { NotificationSettings as Settings, SettingsForm } from '../types'

function SettingsEditor({ saved, onReload }: { saved: Settings; onReload: () => void }) {
  const toast = useToast()
  const location = useLocation()
  const descriptionId = useId()
  const [form, setForm] = useState<SettingsForm>(() => toForm(saved))
  const [errors, setErrors] = useState<SettingsErrors>({})
  const [saving, setSaving] = useState(false)
  const stayRef = useRef<HTMLButtonElement>(null)
  const dirty = isDirty(saved, form)

  // Ask before leaving with unsaved changes (US-021 FE §13.2).
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  // "#channel-<NAME>" in the URL scrolls to that channel row.
  useEffect(() => {
    if (!location.hash) return
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'center' })
  }, [location.hash])

  useEffect(() => {
    track('notification_settings_viewed', { remindersEnabled: saved.remindersEnabled, reminderLeadDays: saved.reminderLeadDays })
    // Logged once per page view.
  }, [])

  function change(next: SettingsForm) {
    setForm(next)
    setErrors(validateSettings(next))
  }

  async function save() {
    const validation = validateSettings(form)
    setErrors(validation)
    if (validation.reminderLeadDays) return
    const patch = buildSettingsPatch(saved, form)
    if (!Object.keys(patch).length) return
    setSaving(true)
    try {
      const updated = await updateNotificationSettings(patch)
      setQueryData(NOTIFICATION_SETTINGS_KEY, updated)
      setForm(toForm(updated))
      toast.show('Đã lưu cài đặt thông báo. Thay đổi áp dụng từ lần kiểm tra kế tiếp.', 'success')
      track('notification_settings_saved', {
        remindersEnabled: updated.remindersEnabled,
        reminderLeadDays: updated.reminderLeadDays,
        enabledChannels: updated.channels.filter(channel => channel.enabled).map(channel => channel.channel).join(','),
      })
    } catch (error) {
      if (!isApiError(error)) throw error
      track('notification_settings_save_failed', { errorCode: error.code })
      switch (error.code) {
        case 'INVALID_LEAD_DAYS':
          setErrors(current => ({ ...current, reminderLeadDays: 'Số ngày nhắc trước phải từ 0 đến 30.' }))
          break
        case 'CHANNEL_NOT_AVAILABLE':
          toast.show('Kênh này chưa được hỗ trợ.', 'error')
          onReload()
          break
        case 'NETWORK_ERROR':
        case 'TIMEOUT_ERROR':
          toast.show('Không có kết nối mạng. Vui lòng thử lại.', 'error')
          break
        default:
          toast.show('Không lưu được cài đặt. Vui lòng thử lại.', 'error')
      }
    } finally {
      setSaving(false)
    }
  }

  const off = !form.remindersEnabled

  return (
    <>
      <div className="space-y-6 pb-28">
        <Card className="p-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald/10 flex items-center justify-center flex-shrink-0">
              <BellRing className="w-5 h-5 text-emerald" aria-hidden />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground">Bật nhắc bảo dưỡng</p>
              <p id={descriptionId} className="text-sm text-muted mt-1">
                Nhận thông báo khi xe sắp đến mốc bảo dưỡng hoặc đã quá hạn.
              </p>
            </div>
            <Switch
              checked={form.remindersEnabled}
              onChange={checked => change({ ...form, remindersEnabled: checked })}
              label="Bật nhắc bảo dưỡng"
              describedBy={descriptionId}
              disabled={saving}
            />
          </div>

          <div className={cn('mt-6 pt-6 border-t border-border transition-opacity', off && 'opacity-50')}>
            <NumberStepper
              label="Nhắc trước hạn"
              unit="ngày"
              min={0}
              max={30}
              value={form.reminderLeadDays}
              onChange={value => change({ ...form, reminderLeadDays: value })}
              disabled={off || saving}
              error={errors.reminderLeadDays}
              decreaseLabel="Giảm một ngày"
              increaseLabel="Tăng một ngày"
              helper={
                <>
                  0 = nhắc đúng ngày đến hạn. Mặc định: {saved.defaultReminderLeadDays} ngày.{' '}
                  {Number(form.reminderLeadDays) !== saved.defaultReminderLeadDays && !off && (
                    <button
                      type="button"
                      className="text-emerald hover:text-emerald-bright"
                      onClick={() => change({ ...form, reminderLeadDays: String(saved.defaultReminderLeadDays) })}
                    >
                      Đặt về mặc định
                    </button>
                  )}
                </>
              }
            />
            {/* TODO(spec): the km threshold (DUE_SOON_KM) is not returned by this API (Q-FE-NOTI-03). */}
            <p className="text-xs text-muted mt-2">Bạn cũng được nhắc khi xe sắp chạm mốc km bảo dưỡng.</p>
          </div>
        </Card>

        <Card className={cn('p-6 transition-opacity', off && 'opacity-50')}>
          <p className="text-sm font-semibold text-foreground">Kênh nhận thông báo</p>
          <p className="text-sm text-muted mt-1 mb-4">Nhắc bảo dưỡng luôn hiện trong mục Thông báo của ứng dụng. Các kênh bên ngoài dưới đây sẽ được hỗ trợ sau.</p>
          <NotificationChannelList
            channels={saved.channels}
            values={form.channels}
            onChange={(channel, enabled) => change({ ...form, channels: { ...form.channels, [channel]: enabled } })}
            disabled={off || saving}
          />
        </Card>

        <Notice icon={<Info className="w-4 h-4" />}>Thay đổi áp dụng từ lần kiểm tra kế tiếp (08:00 hằng ngày).</Notice>
      </div>

      <div className="fixed bottom-0 left-0 right-0 lg:left-60 z-30 bg-surface border-t border-border">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 py-3 flex gap-2 justify-end">
          <Button variant="secondary" className="flex-1 sm:flex-none" disabled={!dirty || saving} onClick={() => change(toForm(saved))}>
            Huỷ thay đổi
          </Button>
          <Button
            className="flex-1 sm:flex-none"
            onClick={() => void save()}
            loading={saving}
            disabled={!dirty || Boolean(errors.reminderLeadDays)}
          >
            Lưu
          </Button>
        </div>
      </div>

      <Dialog
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        role="alertdialog"
        title="Bạn có thay đổi chưa lưu. Rời trang?"
        initialFocusRef={stayRef}
        footer={
          <>
            <Button ref={stayRef} variant="secondary" onClick={() => blocker.reset?.()}>
              Ở lại
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Rời trang
            </Button>
          </>
        }
      />
    </>
  )
}

/** SCR-501 — maintenance reminder & channel settings (US-021 FE). */
export default function NotificationSettings() {
  const settings = useNotificationSettings()
  useOnboardingRequiredRedirect(settings.error)

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-2xl">
      <Link to="/notifications" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground transition-colors mb-4">
        <ArrowLeft className="w-4 h-4" />
        Thông báo
      </Link>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Cài đặt thông báo</h1>
        <p className="text-sm text-muted mt-1">Chọn thời điểm và kênh nhận nhắc bảo dưỡng.</p>
      </div>

      {settings.data ? (
        <SettingsEditor saved={settings.data} onReload={() => void settings.refetch()} />
      ) : settings.error ? (
        <Card>
          <ErrorState
            title="Không tải được cài đặt thông báo."
            traceId={settings.error.traceId}
            onRetry={() => void settings.refetch()}
            retrying={settings.isFetching}
          />
        </Card>
      ) : (
        <div className="space-y-6">
          <SkeletonCard lines={3} />
          <SkeletonCard lines={5} />
        </div>
      )}
    </div>
  )
}
