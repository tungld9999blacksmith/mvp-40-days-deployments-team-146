import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { isApiError } from '@/shared/api/client'
import { WORKSHOP_CONSENT_POLICY_VERSION } from '@/shared/config/env'
import Button from '@/shared/ui/Button'
import Checkbox from '@/shared/ui/Checkbox'
import { TextInput } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import SupportLink from '@/shared/ui/SupportLink'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { submitErrorMessage } from '@/features/auth/onboarding/errors'
import { isValidFullName, isValidNationalId, isValidPhone, normalizeNationalId } from '@/features/auth/validation'
import { useWorkshopAuth } from '../../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../../navigation'
import * as workshopApi from '../../api'
import { useWorkshopOnboarding } from '../WorkshopOnboardingContext'

interface Form {
  fullName: string
  phoneNumber: string
  nationalId: string
  consentGranted: boolean
}
type Key = keyof Form
const ORDER: Key[] = ['fullName', 'phoneNumber', 'nationalId', 'consentGranted']

function validate(key: Key, form: Form): string | undefined {
  switch (key) {
    case 'fullName':
      return isValidFullName(form.fullName) ? undefined : 'Vui lòng nhập họ tên hợp lệ.'
    case 'phoneNumber':
      return isValidPhone(form.phoneNumber) ? undefined : 'Số điện thoại không hợp lệ.'
    case 'nationalId':
      if (!form.nationalId.trim()) return 'Vui lòng nhập số CCCD.'
      return isValidNationalId(form.nationalId) ? undefined : 'Số CCCD phải gồm đúng 12 chữ số.'
    case 'consentGranted':
      return form.consentGranted ? undefined : 'Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.'
  }
}

/** SCR-202 — owner info incl. national id (US-009 FE §4.2). */
export default function OwnerProfileStep() {
  const navigate = useNavigate()
  const toast = useToast()
  const { owner, onboarding, setOnboarding } = useWorkshopAuth()
  const { snapshot, snapshotError, loadingSnapshot, loadSnapshot, focusField, setFocusField } = useWorkshopOnboarding()
  const [form, setForm] = useState<Form>({ fullName: '', phoneNumber: '', nationalId: '', consentGranted: false })
  const [errors, setErrors] = useState<Partial<Record<Key, string>>>({})
  const [nationalIdHint, setNationalIdHint] = useState<string | null>(null)
  const [nationalIdTaken, setNationalIdTaken] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<{ message: string; traceId: string | null } | null>(null)
  const prefilled = useRef(false)
  const refs = useRef<Partial<Record<Key, HTMLInputElement | null>>>({})

  useEffect(() => {
    if (!snapshot || prefilled.current) return
    prefilled.current = true
    setForm({
      fullName: snapshot.profile.fullName ?? owner?.displayName ?? '',
      phoneNumber: snapshot.profile.phoneNumber ?? '',
      nationalId: '', // only the masked value is ever returned
      consentGranted: snapshot.consents.personalDataProcessing?.granted ?? false,
    })
  }, [snapshot, owner])

  useEffect(() => {
    if (focusField !== 'nationalId' || !snapshot) return
    refs.current.nationalId?.focus()
    setFocusField(null)
  }, [focusField, snapshot, setFocusField])

  if (onboarding && !['ONBOARDING_IN_PROGRESS', 'VERIFICATION_FAILED'].includes(onboarding.status)) {
    return <Navigate to={resolveWorkshopRoute(onboarding)} replace />
  }
  if (!snapshot) {
    if (snapshotError && !loadingSnapshot) return <ErrorState traceId={snapshotError.traceId} onRetry={() => void loadSnapshot()} />
    return <SkeletonCard lines={4} />
  }

  const masked = nationalIdHint ?? snapshot.profile.nationalIdMasked

  function update<K extends Key>(key: K, value: Form[K]) {
    setForm(current => ({ ...current, [key]: value }))
    if (key === 'nationalId') setNationalIdTaken(false)
    if (errors[key]) setErrors(current => ({ ...current, [key]: undefined }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    const next: Partial<Record<Key, string>> = {}
    for (const key of ORDER) next[key] = validate(key, form)
    setErrors(next)
    const first = ORDER.find(key => next[key])
    if (first) {
      refs.current[first]?.focus()
      return
    }
    setSubmitting(true)
    try {
      const result = await workshopApi.updateProfile({
        fullName: form.fullName.trim().replace(/\s+/g, ' '),
        phoneNumber: form.phoneNumber.trim(),
        nationalId: normalizeNationalId(form.nationalId),
        personalDataConsent: { granted: true, policyVersion: WORKSHOP_CONSENT_POLICY_VERSION },
      })
      // Do not keep the national id in memory longer than needed (US-009 FE §12.3).
      setForm(current => ({ ...current, nationalId: '' }))
      setNationalIdHint(result.profile.nationalIdMasked)
      setOnboarding(result.onboarding)
      void loadSnapshot()
      track('workshop_onboarding_profile_submitted')
      navigate(result.onboarding.nextStep === 'WORKSHOP' ? '/workshop/onboarding/operations' : resolveWorkshopRoute(result.onboarding))
    } catch (error) {
      if (!isApiError(error)) throw error
      switch (error.code) {
        case 'INVALID_FIELD_FORMAT': {
          const key = (error.field ?? 'fullName') as Key
          setErrors(current => ({ ...current, [key]: error.message || 'Dữ liệu không hợp lệ.' }))
          refs.current[key]?.focus()
          break
        }
        case 'PHONE_ALREADY_IN_USE':
          setErrors(current => ({ ...current, phoneNumber: 'Số điện thoại đã được sử dụng bởi chủ xưởng khác.' }))
          break
        case 'NATIONAL_ID_ALREADY_IN_USE':
          setErrors(current => ({ ...current, nationalId: 'Số CCCD đã được sử dụng bởi tài khoản chủ xưởng khác.' }))
          setNationalIdTaken(true)
          refs.current.nationalId?.focus()
          break
        case 'CONSENT_REQUIRED':
          setErrors(current => ({ ...current, consentGranted: 'Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.' }))
          break
        case 'VERIFICATION_IN_PROGRESS':
        case 'ONBOARDING_ALREADY_COMPLETED': {
          const data = await loadSnapshot()
          if (data) navigate(resolveWorkshopRoute(data.onboarding), { replace: true })
          break
        }
        default:
          if (error.status >= 500 || error.status === 0) setFormError({ message: submitErrorMessage(error), traceId: error.traceId })
          else toast.show(submitErrorMessage(error), 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const bind = (key: Key) => ({
    ref: (element: HTMLInputElement | null) => {
      refs.current[key] = element
    },
    onBlur: () => setErrors(current => ({ ...current, [key]: validate(key, form) })),
    error: errors[key],
    disabled: submitting,
  })

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Thông tin chủ xưởng</h1>
        <p className="text-sm text-muted mt-1">Gmail và số CCCD dùng để hãng xác nhận bạn là người quản lý xưởng.</p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5">
        <TextInput
          label="Email Google"
          value={snapshot.profile.email || owner?.email || ''}
          readOnly
          disabled
          helper="Dùng đúng Gmail đã đăng ký với hãng làm người quản lý xưởng."
        />
        <TextInput
          label="Họ tên"
          required
          autoComplete="name"
          value={form.fullName}
          onChange={e => update('fullName', e.target.value)}
          {...bind('fullName')}
        />
        <TextInput
          label="Số điện thoại"
          required
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={form.phoneNumber}
          onChange={e => update('phoneNumber', e.target.value)}
          {...bind('phoneNumber')}
        />
        <TextInput
          label="Số CCCD"
          required
          inputMode="numeric"
          autoComplete="off"
          className="font-mono"
          placeholder={masked ? `CCCD đã lưu: ${masked}` : '12 chữ số'}
          helper={masked ? 'Nhập lại đầy đủ số CCCD khi cập nhật thông tin.' : undefined}
          value={form.nationalId}
          onChange={e => update('nationalId', e.target.value)}
          {...bind('nationalId')}
        />
        {nationalIdTaken && <SupportLink label="Liên hệ hãng" />}
      </section>

      <Checkbox
        checked={form.consentGranted}
        onChange={checked => update('consentGranted', checked)}
        disabled={submitting}
        error={errors.consentGranted}
        label="Tôi đồng ý với điều khoản xử lý dữ liệu cá nhân."
        description={`Phiên bản điều khoản ${WORKSHOP_CONSENT_POLICY_VERSION}.`}
      />

      {formError && (
        <Notice tone="error" role="alert" title={formError.message}>
          {formError.traceId && <span className="font-mono text-xs">Mã lỗi: {formError.traceId}</span>}
        </Notice>
      )}

      <div className="flex flex-col gap-3">
        <Button type="submit" size="lg" fullWidth loading={submitting} loadingText="Đang lưu...">
          Tiếp tục
        </Button>
        {onboarding?.profileCompleted && (
          <Button variant="ghost" fullWidth disabled={submitting} onClick={() => navigate('/workshop/onboarding/operations')}>
            Giữ thông tin đã lưu, sang bước 2
          </Button>
        )}
      </div>
    </form>
  )
}
