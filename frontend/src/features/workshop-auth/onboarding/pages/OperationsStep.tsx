import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR } from '@/shared/api/client'
import { WORKSHOP_CONSENT_POLICY_VERSION } from '@/shared/config/env'
import Button from '@/shared/ui/Button'
import Checkbox from '@/shared/ui/Checkbox'
import { TextArea, TextInput } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { submitErrorMessage } from '@/features/auth/onboarding/errors'
import { isValidHotline } from '@/features/auth/validation'
import { useWorkshopAuth } from '../../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../../navigation'
import { defaultOperatingHours, normalizeOperatingHours, validateOperatingHours } from '../../operatingHours'
import * as workshopApi from '../../api'
import { useWorkshopOnboarding, type OperationsFormState } from '../WorkshopOnboardingContext'
import OperatingHoursEditor from '../components/OperatingHoursEditor'

type Errors = Record<string, string>

function validateForm(form: OperationsFormState): Errors {
  const errors: Errors = {}
  const address = form.address.trim()
  if (address.length < 5 || address.length > 500) errors.address = 'Vui lòng nhập địa chỉ xưởng (tối thiểu 5 ký tự).'

  const hasLat = form.latitude.trim() !== ''
  const hasLng = form.longitude.trim() !== ''
  const lat = Number(form.latitude)
  const lng = Number(form.longitude)
  if (hasLat !== hasLng || (hasLat && (Number.isNaN(lat) || lat < -90 || lat > 90)) || (hasLng && (Number.isNaN(lng) || lng < -180 || lng > 180))) {
    errors.latitude = 'Vui lòng nhập đủ vĩ độ và kinh độ hợp lệ, hoặc để trống cả hai.'
  }

  if (!form.hotline.trim() || !isValidHotline(form.hotline)) errors.hotline = 'Số hotline không hợp lệ.'

  const technicians = Number(form.totalTechnicians)
  if (!Number.isInteger(technicians) || technicians < 1 || technicians > 200) {
    errors.totalTechnicians = 'Số kỹ thuật viên phải từ 1 đến 200.'
  }
  const reserved = form.emergencySlotsReserved.trim() === '' ? 0 : Number(form.emergencySlotsReserved)
  if (!Number.isInteger(reserved) || reserved < 0) errors.emergencySlotsReserved = 'Số slot dự phòng không hợp lệ.'
  else if (!errors.totalTechnicians && reserved > technicians) {
    errors.emergencySlotsReserved = 'Số slot dự phòng không được vượt quá số kỹ thuật viên.'
  }

  Object.assign(errors, validateOperatingHours(form.operatingHours))
  if (!form.consentGranted) errors.consentGranted = 'Bạn cần đồng ý chia sẻ Gmail và CCCD cho hãng để xác thực.'
  return errors
}

const FIELD_ORDER = ['address', 'latitude', 'hotline', 'totalTechnicians', 'emergencySlotsReserved']

/** SCR-203 — operations + operating hours, then Gmail + CCCD verification (US-009 FE §4.3, §7.4). */
export default function OperationsStep() {
  const navigate = useNavigate()
  const toast = useToast()
  const { onboarding, setOnboarding, setWorkshop } = useWorkshopAuth()
  const { snapshot, snapshotError, loadingSnapshot, loadSnapshot, operationsForm, setOperationsForm, setOutcome } =
    useWorkshopOnboarding()
  const [form, setForm] = useState<OperationsFormState>(
    operationsForm ?? {
      address: '',
      latitude: '',
      longitude: '',
      hotline: '',
      totalTechnicians: '',
      emergencySlotsReserved: '0',
      operatingHours: defaultOperatingHours(),
      consentGranted: false,
    },
  )
  const [errors, setErrors] = useState<Errors>({})
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<{ message: string; traceId: string | null } | null>(null)
  const prefilled = useRef(Boolean(operationsForm))
  const submitted = useRef(false)
  const refs = useRef<Record<string, HTMLElement | null>>({})
  const hourRefs = useRef<Record<number, HTMLInputElement | null>>({})

  useEffect(() => {
    if (prefilled.current || !snapshot) return
    prefilled.current = true
    const registration = snapshot.registration
    if (!registration) {
      setForm(current => ({ ...current, consentGranted: snapshot.consents.oemDataSharing?.granted ?? false }))
      return
    }
    setForm({
      address: registration.address,
      latitude: registration.latitude?.toString() ?? '',
      longitude: registration.longitude?.toString() ?? '',
      hotline: registration.hotline,
      totalTechnicians: String(registration.totalTechnicians),
      emergencySlotsReserved: String(registration.emergencySlotsReserved),
      operatingHours: registration.operatingHours.length ? normalizeOperatingHours(registration.operatingHours) : defaultOperatingHours(),
      consentGranted: snapshot.consents.oemDataSharing?.granted ?? false,
    })
  }, [snapshot])

  // `submitted`: the submit itself navigates to its result; the new status must not redirect first.
  if (!submitted.current && onboarding && (!onboarding.profileCompleted || !['ONBOARDING_IN_PROGRESS', 'VERIFICATION_FAILED'].includes(onboarding.status))) {
    return <Navigate to={resolveWorkshopRoute(onboarding)} replace />
  }
  if (!snapshot) {
    if (snapshotError && !loadingSnapshot) return <ErrorState traceId={snapshotError.traceId} onRetry={() => void loadSnapshot()} />
    return <SkeletonCard lines={6} />
  }

  function update<K extends keyof OperationsFormState>(key: K, value: OperationsFormState[K]) {
    setForm(current => ({ ...current, [key]: value }))
    setErrors(current => {
      const next = { ...current }
      delete next[key]
      if (key === 'totalTechnicians' || key === 'emergencySlotsReserved') {
        delete next.totalTechnicians
        delete next.emergencySlotsReserved
      }
      if (key === 'latitude' || key === 'longitude') delete next.latitude
      if (key === 'operatingHours') {
        for (const errorKey of Object.keys(next)) if (errorKey.startsWith('operatingHours')) delete next[errorKey]
      }
      return next
    })
  }

  function focusFirst(errs: Errors) {
    const field = FIELD_ORDER.find(key => errs[key])
    if (field) return refs.current[field]?.focus()
    const dayKey = Object.keys(errs).find(key => key.startsWith('operatingHours['))
    if (dayKey) {
      const index = Number(/\[(\d+)\]/.exec(dayKey)?.[1] ?? 0)
      return hourRefs.current[index]?.focus()
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    const nextErrors = validateForm(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      focusFirst(nextErrors)
      return
    }

    setOperationsForm(form)
    setSubmitting(true)
    const hours = normalizeOperatingHours(form.operatingHours)
    track('workshop_verification_submitted', {
      totalTechnicians: Number(form.totalTechnicians),
      openDays: hours.filter(hour => !hour.isClosed).length,
    })
    const body = {
      address: form.address.trim(),
      latitude: form.latitude.trim() ? Number(form.latitude) : null,
      longitude: form.longitude.trim() ? Number(form.longitude) : null,
      hotline: form.hotline.trim(),
      totalTechnicians: Number(form.totalTechnicians),
      emergencySlotsReserved: form.emergencySlotsReserved.trim() ? Number(form.emergencySlotsReserved) : 0,
      operatingHours: hours,
      oemDataSharingConsent: { granted: true, policyVersion: WORKSHOP_CONSENT_POLICY_VERSION },
    }
    const key = newId()

    try {
      let response
      try {
        response = await workshopApi.submitWorkshopVerification(body, key)
      } catch (error) {
        if (!(isApiError(error) && (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR))) throw error
        response = await workshopApi.submitWorkshopVerification(body, key)
      }
      const { data, status } = response
      submitted.current = true
      setOnboarding(data.onboarding)
      if (data.workshop) setWorkshop(data.workshop)
      setOutcome({
        attempt: data.verification,
        failureReason: data.verification.failureReason,
        retryAfterSeconds: null,
        workshop: data.workshop,
      })
      track('workshop_verification_result', { status: data.verification.status, failureReason: data.verification.failureReason })
      if (status === 202 || data.verification.status === 'PENDING') navigate('/workshop/onboarding/verifying', { replace: true })
      else if (data.verification.status === 'VERIFIED') navigate('/workshop/onboarding/success', { replace: true })
      else navigate('/workshop/onboarding/failed', { replace: true })
    } catch (error) {
      if (!isApiError(error)) throw error
      switch (error.code) {
        case 'INVALID_FIELD_FORMAT': {
          const field = error.field ?? 'address'
          const next = { ...errors, [field === 'longitude' ? 'latitude' : field]: error.message || 'Dữ liệu không hợp lệ.' }
          setErrors(next)
          focusFirst(next)
          break
        }
        case 'CONSENT_REQUIRED':
          setErrors(current => ({ ...current, consentGranted: 'Bạn cần đồng ý chia sẻ Gmail và CCCD cho hãng để xác thực.' }))
          break
        case 'WORKSHOP_ALREADY_CLAIMED':
          setOutcome({ attempt: null, failureReason: 'ALREADY_CLAIMED', retryAfterSeconds: null, workshop: null })
          await loadSnapshot()
          navigate('/workshop/onboarding/failed', { replace: true })
          break
        case 'VERIFICATION_ATTEMPTS_EXCEEDED':
          setOutcome({ attempt: null, failureReason: null, retryAfterSeconds: error.retryAfter, workshop: null })
          await loadSnapshot()
          navigate('/workshop/onboarding/failed', { replace: true })
          break
        case 'VERIFICATION_IN_PROGRESS':
        case 'PROFILE_INCOMPLETE':
        case 'ONBOARDING_ALREADY_COMPLETED': {
          const data = await loadSnapshot()
          if (data) navigate(resolveWorkshopRoute(data.onboarding), { replace: true })
          break
        }
        case 'IDEMPOTENCY_KEY_REUSED':
          toast.show('Vui lòng nhấn gửi lại.', 'warning')
          break
        default:
          setFormError({ message: submitErrorMessage(error), traceId: error.traceId })
      }
    } finally {
      setSubmitting(false)
    }
  }

  const refFor = (key: string) => (element: HTMLElement | null) => {
    refs.current[key] = element
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Vận hành xưởng</h1>
        <p className="text-sm text-muted mt-1">
          Tên xưởng, khu vực và loại xưởng sẽ lấy từ hãng. Bạn chỉ cần khai báo thông tin vận hành.
        </p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5 elevation-sm">
        <h2 className="text-sm font-semibold text-foreground">Vị trí & liên hệ</h2>
        <TextArea
          ref={refFor('address')}
          label="Địa chỉ xưởng"
          required
          rows={2}
          value={form.address}
          error={errors.address}
          disabled={submitting}
          onChange={e => update('address', e.target.value)}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <TextInput
            ref={refFor('latitude')}
            label="Vĩ độ"
            optional
            inputMode="decimal"
            className="font-mono"
            placeholder="21.017"
            value={form.latitude}
            error={errors.latitude}
            disabled={submitting}
            onChange={e => update('latitude', e.target.value)}
          />
          <TextInput
            label="Kinh độ"
            optional
            inputMode="decimal"
            className="font-mono"
            placeholder="105.781"
            value={form.longitude}
            disabled={submitting}
            onChange={e => update('longitude', e.target.value)}
          />
        </div>
        <TextInput
          ref={refFor('hotline')}
          label="Hotline xưởng"
          required
          type="tel"
          inputMode="tel"
          className="font-mono"
          placeholder="024 3765 4321"
          value={form.hotline}
          error={errors.hotline}
          disabled={submitting}
          onChange={e => update('hotline', e.target.value)}
        />
      </section>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5 elevation-sm">
        <h2 className="text-sm font-semibold text-foreground">Công suất</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <TextInput
            ref={refFor('totalTechnicians')}
            label="Số kỹ thuật viên mỗi ca"
            required
            type="number"
            inputMode="numeric"
            min={1}
            max={200}
            className="font-mono"
            value={form.totalTechnicians}
            error={errors.totalTechnicians}
            disabled={submitting}
            onChange={e => update('totalTechnicians', e.target.value)}
          />
          <TextInput
            ref={refFor('emergencySlotsReserved')}
            label="Slot dự phòng khẩn cấp"
            type="number"
            inputMode="numeric"
            min={0}
            className="font-mono"
            helper="Số slot giữ lại cho trường hợp khẩn cấp, không vượt quá số kỹ thuật viên."
            value={form.emergencySlotsReserved}
            error={errors.emergencySlotsReserved}
            disabled={submitting}
            onChange={e => update('emergencySlotsReserved', e.target.value)}
          />
        </div>
      </section>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 elevation-sm">
        <h2 className="text-sm font-semibold text-foreground mb-4">Giờ hoạt động</h2>
        <OperatingHoursEditor
          value={form.operatingHours}
          onChange={hours => update('operatingHours', hours)}
          errors={errors}
          disabled={submitting}
          firstInvalidRef={(element, index) => {
            hourRefs.current[index] = element
          }}
        />
      </section>

      <Checkbox
        checked={form.consentGranted}
        onChange={checked => update('consentGranted', checked)}
        disabled={submitting}
        error={errors.consentGranted}
        label="Tôi đồng ý chia sẻ Gmail và số CCCD cho hãng để xác thực người quản lý xưởng."
      />

      {submitting && (
        <Notice role="status" icon={<ShieldCheck className="w-4 h-4 text-emerald" />}>
          Đang xác thực thông tin của bạn với hãng...
        </Notice>
      )}
      {formError && (
        <Notice tone="error" role="alert" title={formError.message}>
          {formError.traceId && <span className="font-mono text-xs">Mã lỗi: {formError.traceId}</span>}
        </Notice>
      )}

      <div className="flex flex-col-reverse sm:flex-row gap-3 sm:sticky sm:bottom-4">
        <Button
          variant="secondary"
          size="lg"
          disabled={submitting}
          icon={<ArrowLeft className="w-4 h-4" />}
          onClick={() => {
            setOperationsForm(form)
            navigate('/workshop/onboarding/profile')
          }}
        >
          Quay lại
        </Button>
        <Button type="submit" size="lg" className="flex-1" loading={submitting} loadingText="Đang gửi...">
          Gửi xác thực
        </Button>
      </div>
    </form>
  )
}
