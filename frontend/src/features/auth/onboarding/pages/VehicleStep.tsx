import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import { CONSENT_POLICY_VERSION } from '@/shared/config/env'
import Button from '@/shared/ui/Button'
import Checkbox from '@/shared/ui/Checkbox'
import { SelectInput, TextInput } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { useAuth } from '../../context/AuthContext'
import { resolveOnboardingRoute } from '../../navigation'
import * as authApi from '../../api'
import type { VehicleVerificationRequest } from '../../types'
import { isValidManufactureYear, isValidPlate, isValidVin, normalizeVin } from '../../validation'
import { useOnboarding, type VehicleFormState } from '../OnboardingContext'
import { fieldMessage, submitErrorMessage } from '../errors'

type FormKey = keyof VehicleFormState
const FIELD_ORDER: FormKey[] = ['vin', 'licensePlate', 'modelId', 'manufactureYear', 'consentGranted']

function validateField(key: FormKey, form: VehicleFormState): string | undefined {
  switch (key) {
    case 'vin':
      if (!form.vin.trim()) return 'Vui lòng nhập số VIN.'
      return isValidVin(form.vin) ? undefined : 'Số VIN phải gồm 17 ký tự chữ và số.'
    case 'licensePlate':
      if (!form.licensePlate.trim()) return 'Vui lòng nhập biển số xe.'
      return isValidPlate(form.licensePlate) ? undefined : 'Biển số xe không hợp lệ.'
    case 'modelId':
      return form.modelId ? undefined : 'Vui lòng chọn mẫu xe.'
    case 'manufactureYear':
      return !form.manufactureYear || isValidManufactureYear(Number(form.manufactureYear))
        ? undefined
        : 'Năm sản xuất không hợp lệ.'
    case 'consentGranted':
      return form.consentGranted ? undefined : 'Bạn cần đồng ý chia sẻ thông tin xe cho hãng để xác thực.'
  }
}

const EMPTY: VehicleFormState = { vin: '', licensePlate: '', modelId: '', manufactureYear: '', consentGranted: false }

function isRetryableNetwork(error: unknown): boolean {
  return isApiError(error) && (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR)
}

/** SCR-003 — vehicle info, then verification with the manufacturer (US-001 FE §4.3, §7.5). */
export default function VehicleStep() {
  const navigate = useNavigate()
  const toast = useToast()
  const { onboarding, setOnboarding } = useAuth()
  const {
    snapshot,
    snapshotError,
    loadingSnapshot,
    loadSnapshot,
    vehicleForm,
    setVehicleForm,
    setOutcome,
    models,
    setModels,
    focusField,
    setFocusField,
  } = useOnboarding()

  const [form, setForm] = useState<VehicleFormState>(vehicleForm ?? EMPTY)
  const [errors, setErrors] = useState<Partial<Record<FormKey, string>>>({})
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<{ message: string; traceId: string | null } | null>(null)
  const [modelsError, setModelsError] = useState<ApiError | null>(null)
  const [modelsLoading, setModelsLoading] = useState(false)
  const prefilled = useRef(Boolean(vehicleForm))
  const refs = useRef<Partial<Record<FormKey, HTMLInputElement | HTMLSelectElement | null>>>({})

  const loadModels = useCallback(() => {
    setModelsLoading(true)
    setModelsError(null)
    authApi
      .getVehicleModels()
      .then(data => setModels(data.items))
      .catch((error: ApiError) => setModelsError(error))
      .finally(() => setModelsLoading(false))
  }, [setModels])

  useEffect(() => {
    if (models === null && !modelsLoading && !modelsError) loadModels()
  }, [models, modelsLoading, modelsError, loadModels])

  // Prefill from the last submitted vehicle (SCR-006 → "Sửa lại thông tin xe").
  useEffect(() => {
    if (prefilled.current || !snapshot) return
    prefilled.current = true
    const { vehicle, consents } = snapshot
    setForm({
      vin: vehicle?.vin ?? '',
      licensePlate: vehicle?.licensePlate ?? '',
      modelId: vehicle?.declaredModelId ?? '',
      manufactureYear: vehicle?.declaredManufactureYear ? String(vehicle.declaredManufactureYear) : '',
      consentGranted: consents.oemDataSharing?.granted ?? false,
    })
  }, [snapshot])

  // Highlight the field the failure reason points at.
  useEffect(() => {
    if (!focusField || !snapshot || !prefilled.current) return
    const key = focusField as FormKey
    if (refs.current[key]) {
      refs.current[key]?.focus()
      setErrors(current => ({ ...current, [key]: validateField(key, form) ?? 'Vui lòng kiểm tra lại thông tin này.' }))
    }
    setFocusField(null)
  }, [focusField, snapshot, form, setFocusField])

  if (onboarding && (!onboarding.profileCompleted || !['ONBOARDING_IN_PROGRESS', 'VERIFICATION_FAILED'].includes(onboarding.status))) {
    return <Navigate to={resolveOnboardingRoute(onboarding)} replace />
  }
  if (!snapshot) {
    if (snapshotError && !loadingSnapshot) {
      return <ErrorState traceId={snapshotError.traceId} onRetry={() => void loadSnapshot()} />
    }
    return <SkeletonCard lines={5} />
  }

  function update<K extends FormKey>(key: K, value: VehicleFormState[K]) {
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

    setVehicleForm(form)
    setSubmitting(true)
    track('onboarding_vehicle_submitted', { modelId: form.modelId })
    const body: VehicleVerificationRequest = {
      vin: normalizeVin(form.vin),
      licensePlate: form.licensePlate.trim(),
      modelId: form.modelId,
      manufactureYear: form.manufactureYear ? Number(form.manufactureYear) : null,
      oemDataSharingConsent: { granted: true, policyVersion: CONSENT_POLICY_VERSION },
    }
    // New key for each click; the automatic network retry reuses it (API-005 §13).
    const idempotencyKey = newId()

    try {
      let response
      try {
        response = await authApi.submitVehicleVerification(body, idempotencyKey)
      } catch (error) {
        if (!isRetryableNetwork(error)) throw error
        response = await authApi.submitVehicleVerification(body, idempotencyKey)
      }
      const { data, status } = response
      setOnboarding(data.onboarding)
      setOutcome({
        result: data.verification,
        failureReason: data.verification.failureReason,
        remainingAttempts: data.verification.remainingAttempts,
        retryAfterSeconds: null,
        vehicle: data.vehicle,
        warranties: data.warranties,
      })
      track('vehicle_verification_result', {
        status: data.verification.status,
        failureReason: data.verification.failureReason,
        remainingAttempts: data.verification.remainingAttempts,
      })
      if (status === 202 || data.verification.status === 'PENDING') navigate('/onboarding/verifying', { replace: true })
      else if (data.verification.status === 'VERIFIED') navigate('/onboarding/success', { replace: true })
      else navigate('/onboarding/failed', { replace: true })
    } catch (error) {
      if (!isApiError(error)) throw error
      switch (error.code) {
        case 'INVALID_FIELD_FORMAT': {
          const key = (error.field ?? 'vin') as FormKey
          setErrors(current => ({ ...current, [key]: fieldMessage(key) }))
          refs.current[key]?.focus()
          break
        }
        case 'CONSENT_REQUIRED':
          setErrors(current => ({ ...current, consentGranted: 'Bạn cần đồng ý chia sẻ thông tin xe cho hãng để xác thực.' }))
          break
        case 'VEHICLE_ALREADY_LINKED': {
          setOutcome({
            result: null,
            failureReason: 'ALREADY_LINKED',
            remainingAttempts: null,
            retryAfterSeconds: null,
            vehicle: null,
            warranties: [],
          })
          await loadSnapshot()
          navigate('/onboarding/failed', { replace: true })
          break
        }
        case 'VERIFICATION_ATTEMPTS_EXCEEDED': {
          setOutcome({
            result: null,
            failureReason: null,
            remainingAttempts: 0,
            retryAfterSeconds: error.retryAfter,
            vehicle: null,
            warranties: [],
          })
          await loadSnapshot()
          navigate('/onboarding/failed', { replace: true })
          break
        }
        case 'VERIFICATION_IN_PROGRESS':
        case 'PROFILE_INCOMPLETE':
        case 'ONBOARDING_ALREADY_COMPLETED': {
          const data = await loadSnapshot()
          if (data) navigate(resolveOnboardingRoute(data.onboarding), { replace: true })
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

  const bind = (key: FormKey) => ({
    ref: (element: HTMLInputElement | HTMLSelectElement | null) => {
      refs.current[key] = element
    },
    onBlur: () => blur(key),
    error: errors[key],
    disabled: submitting,
  })

  const vinLength = normalizeVin(form.vin).length
  const maxYear = new Date().getFullYear() + 1
  const modelsUnavailable = Boolean(modelsError) || (models !== null && models.length === 0)

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Thông tin xe</h1>
        <p className="text-sm text-muted mt-1">Thông tin xe sẽ được đối chiếu với hệ thống của hãng để xác thực bạn là chủ xe.</p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6 space-y-5">
        <TextInput
          label="Số VIN"
          required
          autoComplete="off"
          spellCheck={false}
          className="font-mono uppercase"
          placeholder="17 ký tự trên giấy đăng ký xe"
          maxLength={20}
          helper="17 ký tự chữ và số, in trên giấy đăng ký hoặc khung xe."
          aside={
            <span className={`text-xs font-mono ${vinLength === 17 ? 'text-emerald' : 'text-muted'}`} aria-live="polite">
              {vinLength}/17
            </span>
          }
          value={form.vin}
          onChange={e => update('vin', e.target.value.toUpperCase())}
          {...bind('vin')}
        />
        <TextInput
          label="Biển số"
          required
          autoComplete="off"
          spellCheck={false}
          className="font-mono uppercase"
          placeholder="30A-123.45"
          value={form.licensePlate}
          onChange={e => update('licensePlate', e.target.value.toUpperCase())}
          {...bind('licensePlate')}
        />
        <SelectInput
          label="Mẫu xe"
          required
          placeholder={modelsLoading ? 'Đang tải mẫu xe...' : 'Chọn mẫu xe'}
          value={form.modelId}
          onChange={e => update('modelId', e.target.value)}
          {...bind('modelId')}
          disabled={submitting || modelsLoading || modelsUnavailable}
        >
          {(models ?? []).map(model => (
            <option key={model.modelId} value={model.modelId}>
              {[model.modelName, model.trim].filter(Boolean).join(' ')}
              {model.productionYear ? ` (${model.productionYear})` : ''}
            </option>
          ))}
        </SelectInput>
        {modelsUnavailable && (
          <Notice
            tone="error"
            action={
              <Button variant="secondary" size="sm" onClick={loadModels} loading={modelsLoading}>
                Thử lại
              </Button>
            }
          >
            {modelsError ? 'Không tải được danh sách mẫu xe.' : 'Chưa có danh sách mẫu xe từ hãng.'}
          </Notice>
        )}
        <TextInput
          label="Năm sản xuất"
          optional
          type="number"
          inputMode="numeric"
          min={2015}
          max={maxYear}
          className="font-mono"
          value={form.manufactureYear}
          onChange={e => update('manufactureYear', e.target.value)}
          {...bind('manufactureYear')}
        />
      </section>

      <Checkbox
        checked={form.consentGranted}
        onChange={checked => update('consentGranted', checked)}
        disabled={submitting}
        error={errors.consentGranted}
        label="Tôi đồng ý chia sẻ thông tin xe (VIN, biển số) cho hãng xe để xác thực quyền sở hữu."
      />

      {submitting && (
        <Notice role="status" icon={<ShieldCheck className="w-4 h-4 text-emerald" />}>
          Đang xác thực thông tin xe của bạn...
        </Notice>
      )}
      {formError && (
        <Notice tone="error" role="alert" title={formError.message}>
          {formError.traceId && <span className="font-mono text-xs">Mã lỗi: {formError.traceId}</span>}
        </Notice>
      )}

      <div className="flex flex-col-reverse sm:flex-row gap-3">
        <Button
          variant="secondary"
          size="lg"
          disabled={submitting}
          icon={<ArrowLeft className="w-4 h-4" />}
          onClick={() => {
            setVehicleForm(form)
            navigate('/onboarding/profile')
          }}
        >
          Quay lại
        </Button>
        <Button
          type="submit"
          size="lg"
          className="flex-1"
          loading={submitting}
          loadingText="Đang xác thực..."
          disabled={modelsUnavailable}
        >
          Xác nhận & Xác thực
        </Button>
      </div>
    </form>
  )
}
