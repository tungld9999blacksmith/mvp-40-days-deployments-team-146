import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { isApiError } from '@/shared/api/client'
import { CONSENT_POLICY_VERSION } from '@/shared/config/env'
import Button from '@/shared/ui/Button'
import Checkbox from '@/shared/ui/Checkbox'
import { SelectInput, TextInput } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { useAuth } from '../../context/AuthContext'
import { resolveOnboardingRoute } from '../../navigation'
import * as authApi from '../../api'
import {
  isValidBirthDate,
  isValidFullName,
  isValidNationalId,
  isValidPhone,
  normalizeNationalId,
} from '../../validation'
import { useOnboarding } from '../OnboardingContext'
import { PROVINCES } from '../provinces'
import { fieldMessage, formKeyForField, submitErrorMessage } from '../errors'

interface ProfileForm {
  fullName: string
  phoneNumber: string
  nationalId: string
  dateOfBirth: string
  addressLine: string
  province: string
  district: string
  ward: string
  consentGranted: boolean
}

type FormKey = keyof ProfileForm
const FIELD_ORDER: FormKey[] = [
  'fullName',
  'phoneNumber',
  'nationalId',
  'dateOfBirth',
  'addressLine',
  'province',
  'district',
  'ward',
  'consentGranted',
]

function validateField(key: FormKey, form: ProfileForm): string | undefined {
  switch (key) {
    case 'fullName':
      if (!form.fullName.trim()) return 'Vui lòng nhập họ tên.'
      return isValidFullName(form.fullName) ? undefined : 'Họ tên không hợp lệ.'
    case 'phoneNumber':
      if (!form.phoneNumber.trim()) return 'Vui lòng nhập số điện thoại.'
      return isValidPhone(form.phoneNumber) ? undefined : 'Số điện thoại không hợp lệ.'
    case 'nationalId':
      if (!form.nationalId.trim()) return 'Vui lòng nhập số CCCD.'
      return isValidNationalId(form.nationalId) ? undefined : 'Số CCCD phải gồm đúng 12 chữ số.'
    case 'dateOfBirth':
      return !form.dateOfBirth || isValidBirthDate(form.dateOfBirth) ? undefined : 'Ngày sinh không hợp lệ.'
    case 'addressLine': {
      const length = form.addressLine.trim().length
      return length >= 5 && length <= 500 ? undefined : 'Vui lòng nhập địa chỉ (tối thiểu 5 ký tự).'
    }
    case 'province':
      return form.province ? undefined : 'Vui lòng chọn tỉnh/thành phố.'
    case 'district':
      return form.district.length <= 100 ? undefined : 'Tối đa 100 ký tự.'
    case 'ward':
      return form.ward.length <= 100 ? undefined : 'Tối đa 100 ký tự.'
    case 'consentGranted':
      return form.consentGranted ? undefined : 'Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.'
  }
}

const EMPTY: ProfileForm = {
  fullName: '',
  phoneNumber: '',
  nationalId: '',
  dateOfBirth: '',
  addressLine: '',
  province: '',
  district: '',
  ward: '',
  consentGranted: false,
}

/** SCR-002 — personal info + nearby location (US-001 FE §4.2). */
export default function ProfileStep() {
  const navigate = useNavigate()
  const toast = useToast()
  const { user, onboarding, setOnboarding } = useAuth()
  const { snapshot, snapshotError, loadingSnapshot, loadSnapshot, focusField, setFocusField } = useOnboarding()
  const [form, setForm] = useState<ProfileForm>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<FormKey, string>>>({})
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<{ message: string; traceId: string | null } | null>(null)
  const prefilled = useRef(false)
  const refs = useRef<Partial<Record<FormKey, HTMLInputElement | HTMLSelectElement | null>>>({})

  // Prefill once from API-002 (resume — AF-002).
  useEffect(() => {
    if (!snapshot || prefilled.current) return
    prefilled.current = true
    const { profile, location, consents } = snapshot
    setForm({
      fullName: profile.fullName ?? profile.displayName ?? user?.displayName ?? '',
      phoneNumber: profile.phoneNumber ?? '',
      nationalId: '',
      dateOfBirth: profile.dateOfBirth ?? '',
      addressLine: location?.addressLine ?? '',
      province: location?.province ?? '',
      district: location?.district ?? '',
      ward: location?.ward ?? '',
      consentGranted: consents.personalDataProcessing?.granted ?? false,
    })
  }, [snapshot, user])

  // Coming back from SCR-006 with NATIONAL_ID_MISMATCH: focus the national id.
  useEffect(() => {
    if (focusField !== 'nationalId' || !snapshot) return
    refs.current.nationalId?.focus()
    setFocusField(null)
  }, [focusField, snapshot, setFocusField])

  if (onboarding && !['ONBOARDING_IN_PROGRESS', 'VERIFICATION_FAILED'].includes(onboarding.status)) {
    return <Navigate to={resolveOnboardingRoute(onboarding)} replace />
  }

  if (!snapshot) {
    if (snapshotError && !loadingSnapshot) {
      return <ErrorState traceId={snapshotError.traceId} onRetry={() => void loadSnapshot()} />
    }
    return <SkeletonCard lines={6} />
  }

  function update<K extends FormKey>(key: K, value: ProfileForm[K]) {
    setForm(current => ({ ...current, [key]: value }))
    if (errors[key]) setErrors(current => ({ ...current, [key]: undefined }))
  }

  function blur(key: FormKey) {
    setErrors(current => ({ ...current, [key]: validateField(key, form) }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    const nextErrors: Partial<Record<FormKey, string>> = {}
    for (const key of FIELD_ORDER) nextErrors[key] = validateField(key, form)
    setErrors(nextErrors)
    const firstInvalid = FIELD_ORDER.find(key => nextErrors[key])
    if (firstInvalid) {
      refs.current[firstInvalid]?.focus()
      return
    }

    setSubmitting(true)
    try {
      const result = await authApi.updateProfile({
        fullName: form.fullName.trim().replace(/\s+/g, ' '),
        phoneNumber: form.phoneNumber.trim(),
        nationalId: normalizeNationalId(form.nationalId),
        dateOfBirth: form.dateOfBirth || null,
        location: {
          addressLine: form.addressLine.trim(),
          ward: form.ward.trim() || null,
          district: form.district.trim() || null,
          province: form.province,
          latitude: null,
          longitude: null,
          source: 'MANUAL',
          placeId: null,
        },
        personalDataConsent: { granted: true, policyVersion: CONSENT_POLICY_VERSION },
      })
      setOnboarding(result.onboarding)
      void loadSnapshot()
      track('onboarding_profile_submitted')
      navigate(result.onboarding.nextStep === 'VEHICLE' ? '/onboarding/vehicle' : resolveOnboardingRoute(result.onboarding))
    } catch (error) {
      if (!isApiError(error)) throw error
      switch (error.code) {
        case 'INVALID_FIELD_FORMAT': {
          const field = error.field ?? ''
          const key = formKeyForField(field) as FormKey
          setErrors(current => ({ ...current, [key]: fieldMessage(field) }))
          refs.current[key]?.focus()
          break
        }
        case 'PHONE_ALREADY_IN_USE':
          setErrors(current => ({ ...current, phoneNumber: 'Số điện thoại đã được sử dụng bởi tài khoản khác.' }))
          refs.current.phoneNumber?.focus()
          break
        case 'NATIONAL_ID_ALREADY_IN_USE':
          setErrors(current => ({ ...current, nationalId: 'Số CCCD đã được sử dụng bởi tài khoản khác.' }))
          refs.current.nationalId?.focus()
          break
        case 'CONSENT_REQUIRED':
          setErrors(current => ({
            ...current,
            consentGranted: 'Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.',
          }))
          break
        case 'VERIFICATION_IN_PROGRESS':
        case 'ONBOARDING_ALREADY_COMPLETED': {
          const data = await loadSnapshot()
          if (data) navigate(resolveOnboardingRoute(data.onboarding), { replace: true })
          break
        }
        default:
          if (error.status >= 500 || error.status === 0) {
            setFormError({ message: submitErrorMessage(error), traceId: error.traceId })
          } else {
            toast.show(submitErrorMessage(error), 'error')
          }
      }
    } finally {
      setSubmitting(false)
    }
  }

  const bind = (key: FormKey) => ({
    ref: (element: HTMLInputElement | HTMLSelectElement | null) => {
      refs.current[key] = element
    },
    onBlur: () => blur(key),
    error: errors[key],
    disabled: submitting,
  })

  const today = new Date().toISOString().slice(0, 10)
  const maskedId = snapshot.profile.nationalIdMasked

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Thông tin cá nhân</h1>
        <p className="text-sm text-muted mt-1">
          Thông tin này dùng để xác thực chủ xe với hãng và gợi ý trung tâm bảo dưỡng gần bạn.
        </p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5 elevation-sm">
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
          placeholder="0901 234 567"
          value={form.phoneNumber}
          onChange={e => update('phoneNumber', e.target.value)}
          {...bind('phoneNumber')}
        />
        {/* TODO(spec): US-001 FE §4.2 has no national id field, but the backend requires
            `nationalId` (12 digits) on PUT /onboarding/profile to verify ownership with the OEM. */}
        <TextInput
          label="Số CCCD"
          required
          inputMode="numeric"
          autoComplete="off"
          className="font-mono placeholder:font-sans"
          placeholder={maskedId ? `CCCD đã lưu: ${maskedId}` : '12 chữ số'}
          helper={maskedId ? 'Nhập lại đầy đủ số CCCD khi cập nhật thông tin.' : 'Dùng để hãng xác nhận bạn là chủ xe.'}
          value={form.nationalId}
          onChange={e => update('nationalId', e.target.value)}
          {...bind('nationalId')}
        />
        <TextInput
          label="Ngày sinh"
          optional
          type="date"
          min="1900-01-01"
          max={today}
          value={form.dateOfBirth}
          onChange={e => update('dateOfBirth', e.target.value)}
          {...bind('dateOfBirth')}
        />
      </section>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5 elevation-sm">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Địa điểm gần bạn</h2>
          <p className="text-xs text-muted mt-1">Khu vực bạn sinh sống hoặc hoạt động chính.</p>
        </div>
        <TextInput
          label="Địa chỉ"
          required
          autoComplete="street-address"
          placeholder="Số nhà, tên đường"
          value={form.addressLine}
          onChange={e => update('addressLine', e.target.value)}
          {...bind('addressLine')}
        />
        <SelectInput
          label="Tỉnh / thành phố"
          required
          placeholder="Chọn tỉnh / thành phố"
          value={form.province}
          onChange={e => update('province', e.target.value)}
          {...bind('province')}
        >
          {form.province && !PROVINCES.includes(form.province) && <option value={form.province}>{form.province}</option>}
          {PROVINCES.map(province => (
            <option key={province} value={province}>
              {province}
            </option>
          ))}
        </SelectInput>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <TextInput
            label="Quận / huyện"
            optional
            value={form.district}
            onChange={e => update('district', e.target.value)}
            {...bind('district')}
          />
          <TextInput
            label="Phường / xã"
            optional
            value={form.ward}
            onChange={e => update('ward', e.target.value)}
            {...bind('ward')}
          />
        </div>
      </section>

      <Checkbox
        checked={form.consentGranted}
        onChange={checked => update('consentGranted', checked)}
        disabled={submitting}
        error={errors.consentGranted}
        label="Tôi đồng ý với điều khoản xử lý dữ liệu cá nhân của EV Care."
        description={`Phiên bản điều khoản ${CONSENT_POLICY_VERSION}.`}
      />

      {formError && (
        <Notice tone="error" role="alert" title={formError.message}>
          {formError.traceId && <span className="font-mono text-xs">Mã lỗi: {formError.traceId}</span>}
        </Notice>
      )}

      <Button type="submit" size="lg" fullWidth loading={submitting} loadingText="Đang lưu...">
        Tiếp tục
      </Button>
    </form>
  )
}
