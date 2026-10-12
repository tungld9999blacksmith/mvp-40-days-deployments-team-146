import { useEffect, useId, useRef, useState } from 'react'
import { Link, useBlocker, useLocation } from 'react-router-dom'
import { ArrowLeft, BellRing, Info } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import { invalidateQueries, setQueryData } from '@/shared/hooks/useCachedQuery'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import NumberStepper from '@/shared/ui/NumberStepper'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import Switch from '@/shared/ui/Switch'
import { cn } from '@/shared/ui/cn'
import { useToast } from '@/shared/ui/Toast'
import { page } from '@/shared/ui/page'
import { track } from '@/shared/utils/track'
import { useOnboardingRequiredRedirect } from '@/features/auth/hooks/useOnboardingRequiredRedirect'
import { NOTIFICATION_SETTINGS_KEY, deletePersonalizationData, updateNotificationSettings } from '../api'
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
  const [deleteOpen, setDeleteOpen] = useState(false)
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
    if (Object.values(validation).some(Boolean)) return
    const patch = buildSettingsPatch(saved, form)
    if (!Object.keys(patch).length) return
    setSaving(true)
    try {
      const updated = await updateNotificationSettings(patch)
      invalidateQueries('maintenance:', 'reminder:')
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
        case 'PERSONALIZATION_CONSENT_REQUIRED':
          toast.show('Thông tin đồng ý đã thay đổi. Vui lòng đọc lại phần cá nhân hoá trước khi lưu.', 'error')
          onReload()
          break
        case 'PERSONALIZATION_UNAVAILABLE':
          toast.show('Nhắc theo mức sử dụng đang tạm tắt trên hệ thống.', 'error')
          onReload()
          break
        case 'EMAIL_NOT_VERIFIED':
          toast.show('Cần email đăng nhập đã xác minh để bật nhận email.', 'error')
          break
        case 'EMAIL_TEST_RECIPIENT_MISMATCH':
          toast.show('Tài khoản demo phải dùng email trùng địa chỉ gửi thử đã cấu hình.', 'error')
          break
        case 'EMAIL_SUPPRESSED':
          toast.show('Địa chỉ email đang bị chặn do lỗi giao nhận trước đó.', 'error')
          break
        case 'DEMO_READ_ONLY':
          toast.show('Tài khoản dùng thử không đổi được cài đặt thông báo.', 'error')
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

  async function erasePersonalization() {
    setSaving(true)
    try {
      const updated = await deletePersonalizationData()
      invalidateQueries('maintenance:', 'reminder:')
      setQueryData(NOTIFICATION_SETTINGS_KEY, updated)
      setForm(toForm(updated))
      setDeleteOpen(false)
      toast.show('Đã tắt cá nhân hoá và xoá dữ liệu suy ra đã lưu.', 'success')
    } catch {
      toast.show('Không xoá được dữ liệu. Vui lòng thử lại.', 'error')
    } finally {
      setSaving(false)
    }
  }

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

        {saved.sendScheduleAvailable && <Card className="p-6 space-y-4">
          <div className="flex items-start gap-4">
            <div className="flex-1"><p className="text-sm font-semibold text-foreground">Giờ nhận nhắc bảo dưỡng</p><p className="text-sm text-muted mt-1">Lời nhắc hiện ngay trong ứng dụng. Các kênh bên ngoài chờ giờ bạn chọn, thường trong vòng 15 phút.</p></div>
            <Switch checked={form.preferredSendTimeEnabled} onChange={checked => change({ ...form, preferredSendTimeEnabled: checked })} label="Chọn giờ nhận nhắc" disabled={saving} />
          </div>
          {form.preferredSendTimeEnabled && <label className="block text-sm text-foreground">Giờ nhận
            <input type="time" step="60" value={form.preferredSendTime} onChange={event => change({ ...form, preferredSendTime: event.target.value })} disabled={saving} aria-invalid={Boolean(errors.preferredSendTime)} className="mt-1 block w-full rounded-lg border border-border bg-background p-3 text-foreground focus-field" />
            {errors.preferredSendTime && <span className="text-error">{errors.preferredSendTime}</span>}
          </label>}
          <div className="flex items-start gap-4">
            <div className="flex-1"><p className="text-sm font-semibold text-foreground">Giờ yên lặng</p><p className="text-sm text-muted mt-1">Tạm ngừng gửi qua kênh bên ngoài, kể cả gửi lại sau lỗi.</p></div>
            <Switch checked={form.quietHoursEnabled} onChange={checked => change({ ...form, quietHoursEnabled: checked })} label="Bật giờ yên lặng" disabled={saving} />
          </div>
          {form.quietHoursEnabled && <div className="grid grid-cols-2 gap-3">
            <label className="text-sm text-foreground">Bắt đầu<input type="time" step="60" value={form.quietHoursStart} onChange={event => change({ ...form, quietHoursStart: event.target.value })} disabled={saving} aria-invalid={Boolean(errors.quietHours)} className="mt-1 block w-full min-w-0 rounded-lg border border-border bg-background p-3 text-foreground focus-field" /></label>
            <label className="text-sm text-foreground">Kết thúc<input type="time" step="60" value={form.quietHoursEnd} onChange={event => change({ ...form, quietHoursEnd: event.target.value })} disabled={saving} aria-invalid={Boolean(errors.quietHours)} className="mt-1 block w-full min-w-0 rounded-lg border border-border bg-background p-3 text-foreground focus-field" /></label>
            {errors.quietHours && <p className="col-span-2 text-sm text-error">{errors.quietHours}</p>}
          </div>}
          <label className="block text-sm text-foreground">Múi giờ
            <select value={form.timezone} onChange={event => change({ ...form, timezone: event.target.value })} disabled={saving} className="mt-1 block w-full rounded-lg border border-border bg-background p-3 text-foreground focus-field">
              {[...new Set(['Asia/Ho_Chi_Minh', 'Asia/Tokyo', 'Asia/Singapore', 'UTC', 'America/New_York', 'Europe/London', form.timezone])].map(zone => <option key={zone} value={zone}>{zone === 'Asia/Ho_Chi_Minh' ? 'Việt Nam (UTC+7)' : zone}</option>)}
            </select>
          </label>
          <p className="text-xs text-muted">Nếu giờ nhận nằm trong giờ yên lặng, thông báo chờ tới khi giờ yên lặng kết thúc. Sau gián đoạn, hệ thống gửi tối đa một thông báo còn phù hợp, không gửi bù hàng loạt.</p>
          {off && <p className="text-sm text-muted">Nhắc tổng đang tắt; giờ nhận vẫn được lưu lại.</p>}
        </Card>}

        {saved.personalizationPolicyVersion && <Card className="p-6 space-y-3" >
          <div id="personalization" className="flex items-start gap-4 scroll-mt-6">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground">Nhắc theo mức sử dụng xe</p>
              <p className="text-sm text-muted mt-1">Dùng lịch sử số km hãng đã cập nhật trong 30 ngày gần đây để dự kiến khi xe tới mốc bảo dưỡng và nhắc bạn sớm hơn. Bật và bấm Lưu để đồng ý dùng dữ liệu này.</p>
            </div>
            <Switch checked={form.personalizedRemindersEnabled} onChange={checked => change({ ...form, personalizedRemindersEnabled: checked })} label="Nhắc theo mức sử dụng xe" disabled={saving || (saved.personalizationAvailable === false && !form.personalizedRemindersEnabled)} />
          </div>
          <p className="text-xs text-muted">Dùng số ngày nhắc trước bạn đã chọn. Bạn vẫn được nhắc khi tới ngưỡng km cố định hoặc hạn theo thời gian. Tắt cá nhân hoá thì dùng cách nhắc cố định.</p>
          {off && <p className="text-sm text-muted">Nhắc tổng đang tắt. Lựa chọn này được giữ lại; chưa tạo hoặc gửi nhắc bảo dưỡng.</p>}
          {saved.personalizationMode === 'shadow' && <p className="text-sm text-muted">Đang đánh giá dự báo; lời nhắc hiện vẫn dùng mốc km và thời gian cố định.</p>}
          {saved.personalizationAvailable === false && <p className="text-sm text-muted">Nhắc theo mức sử dụng chưa được bật trên hệ thống.</p>}
          <div className="flex flex-wrap gap-3">
            <Link className="text-sm text-emerald underline" to="/vehicle">Xem mức sử dụng xe</Link>
            <button type="button" className="text-sm text-muted underline disabled:opacity-50" onClick={() => setDeleteOpen(true)} disabled={saving || dirty}>Xoá dữ liệu suy ra đã lưu</button>
          </div>
        </Card>}

        <Card className={cn('p-6 transition-opacity', off && 'opacity-50')}>
          <p className="text-sm font-semibold text-foreground">Kênh nhận thông báo</p>
          <p className="text-sm text-muted mt-1 mb-4">
            Nhắc bảo dưỡng luôn hiện trong mục Thông báo. Cài đặt áp dụng cho tất cả xe của tài khoản.{' '}
            {saved.channels.some(channel => channel.available)
              ? 'Bật thêm kênh bên dưới để nhận nhắc cả khi không mở ứng dụng.'
              : 'Các kênh bên ngoài dưới đây sẽ được hỗ trợ sau.'}
          </p>
          {saved.emailTransport && <div className="text-sm text-muted mb-4 space-y-2">
            <p>Email nhận: <span className="font-medium text-foreground">{saved.emailRecipient ?? 'Chưa có email'}</span>{saved.emailTransport !== 'resend_test' && <> · {saved.emailVerified ? 'Đã xác minh' : 'Chưa xác minh'}</>}</p>
            <p>Email chỉ dùng cho nhắc mốc bảo dưỡng. {saved.emailTransport === 'resend_test' ? 'Địa chỉ gửi thử nhận tối đa một email nhắc mới trong 7 ngày.' : 'Mỗi xe nhận tối đa một email nhắc mới trong 7 ngày.'}</p>
            {saved.emailSuppressed && <p className="text-error">Địa chỉ này đang bị chặn do lỗi giao nhận.</p>}
            {saved.emailTransport === 'mock' && <p>Đang mô phỏng gửi email. <Link to="/notifications/demo-email" className="text-emerald underline">Mở hộp thư demo</Link></p>}
            {saved.emailTransport === 'resend_test' && <>
              <p>Gửi email thật qua Resend với dữ liệu demo. Thư chỉ gửi khi bạn bấm “Gửi thử email thật”.</p>
              {!saved.emailTestRecipientMatched && <p>Tài khoản demo cần dùng email trùng địa chỉ gửi thử đã cấu hình.</p>}
              <Link to="/notifications/demo-email" className="text-emerald underline">Mở email demo và gửi thử</Link>
            </>}
          </div>}
          <NotificationChannelList
            channels={saved.channels}
            values={form.channels}
            onChange={(channel, enabled) => change({ ...form, channels: { ...form.channels, [channel]: enabled } })}
            disabled={off || saving}
          />
        </Card>

        <Notice icon={<Info className="w-4 h-4" />}>Thay đổi áp dụng từ lần kiểm tra nhắc bảo dưỡng kế tiếp.</Notice>
      </div>

      <div className="fixed bottom-0 left-0 right-0 lg:left-60 z-30 bg-surface border-t border-border">
        <div className="max-w-3xl px-4 sm:px-6 xl:px-8 py-3 flex gap-2 justify-end">
          <Button variant="secondary" className="flex-1 sm:flex-none" disabled={!dirty || saving} onClick={() => change(toForm(saved))}>
            Huỷ thay đổi
          </Button>
          <Button
            className="flex-1 sm:flex-none"
            onClick={() => void save()}
            loading={saving}
            disabled={!dirty || Object.values(errors).some(Boolean)}
          >
            Lưu
          </Button>
        </div>
      </div>

      <Dialog
        open={deleteOpen}
        onClose={() => { if (!saving) setDeleteOpen(false) }}
        role="alertdialog"
        title="Xoá dữ liệu cá nhân hoá?"
        footer={<><Button variant="secondary" onClick={() => setDeleteOpen(false)} disabled={saving}>Huỷ</Button><Button variant="danger" onClick={() => void erasePersonalization()} loading={saving}>Xoá dữ liệu suy ra</Button></>}
      >
        <p className="text-sm text-muted">Tắt nhắc theo mức sử dụng, xoá dữ liệu dự báo đã lưu và dừng các lần gửi cá nhân hoá đang chờ. Lịch sử số km từ hãng và lịch sử bảo dưỡng vẫn được giữ để theo dõi xe.</p>
      </Dialog>

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
    <div className={page('reading')}>
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
