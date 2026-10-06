import { useEffect, useRef, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { TextArea, TextInput } from '@/shared/ui/Field'
import { cn } from '@/shared/ui/cn'
import { formatNumber, formatTime } from '@/shared/utils/format'
import { REASON_LABEL } from '@/shared/domain/bookingLabels'

const REJECT_REASONS = ['FULLY_BOOKED', 'NOT_SUPPORTED_SERVICE', 'WORKSHOP_UNAVAILABLE', 'OTHER']
const CANCEL_REASONS = ['NO_SHOW', 'WORKSHOP_UNAVAILABLE', 'CUSTOMER_REQUEST', 'OTHER']
export const NO_SHOW_GRACE_MINUTES = 30

/** us-037 §4.6 — reason required; "Khác" needs a note; NO_SHOW only 30' after the appointment. */
export function ReasonDialog({
  open,
  mode,
  appointmentAt,
  submitting,
  serverError,
  onClose,
  onConfirm,
}: {
  open: boolean
  mode: 'REJECT' | 'CANCEL'
  appointmentAt: string
  submitting: boolean
  serverError?: string | null
  onClose: () => void
  onConfirm: (reasonCode: string, note: string) => void
}) {
  const [reason, setReason] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const safeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    setReason(null)
    setNote('')
    setError(null)
  }, [open])

  const noShowAt = new Date(new Date(appointmentAt).getTime() + NO_SHOW_GRACE_MINUTES * 60_000)
  const noShowTooEarly = Date.now() < noShowAt.getTime()
  const reasons = mode === 'REJECT' ? REJECT_REASONS : CANCEL_REASONS

  function submit() {
    if (!reason) return setError('Vui lòng chọn lý do.')
    if (reason === 'OTHER' && !note.trim()) return setError('Vui lòng ghi rõ lý do.')
    setError(null)
    onConfirm(reason, note.trim())
  }

  return (
    <Dialog
      open={open}
      onClose={() => !submitting && onClose()}
      role="alertdialog"
      title={mode === 'REJECT' ? 'Từ chối yêu cầu giữ chỗ' : 'Huỷ lịch hẹn'}
      description={reason === 'NO_SHOW' ? undefined : 'Khách sẽ nhận được thông báo.'}
      initialFocusRef={safeRef}
      dismissable={!submitting}
      className="sm:max-w-md"
      footer={
        <>
          <Button ref={safeRef} variant="secondary" onClick={onClose} disabled={submitting}>
            Để sau
          </Button>
          <Button variant="danger" loading={submitting} loadingText="Đang gửi…" onClick={submit}>
            {mode === 'REJECT' ? 'Từ chối' : 'Huỷ lịch'}
          </Button>
        </>
      }
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-foreground mb-2">Lý do</legend>
        {reasons.map(code => {
          const disabled = code === 'NO_SHOW' && noShowTooEarly
          return (
            <label
              key={code}
              className={cn(
                'flex items-start gap-3 rounded-xl border px-3.5 py-2.5 text-sm cursor-pointer transition-colors',
                reason === code ? 'border-emerald/50 bg-emerald/5' : 'border-border hover:bg-card-hover',
                disabled && 'opacity-50 cursor-not-allowed hover:bg-transparent',
              )}
            >
              <input
                type="radio"
                name="reason"
                value={code}
                disabled={disabled || submitting}
                checked={reason === code}
                onChange={() => setReason(code)}
                className="mt-0.5 accent-emerald"
              />
              <span>
                <span className="text-foreground">{REASON_LABEL[code]}</span>
                {disabled && <span className="block text-xs text-muted">Có thể chọn sau {formatTime(noShowAt)}</span>}
              </span>
            </label>
          )
        })}
      </fieldset>
      {reason === 'OTHER' && (
        <div className="mt-3">
          <TextArea
            label="Ghi chú"
            required
            rows={3}
            maxLength={255}
            value={note}
            disabled={submitting}
            onChange={event => setNote(event.target.value)}
            aside={<span className="text-xs text-muted font-mono">{note.length}/255</span>}
          />
        </div>
      )}
      {(error || serverError) && (
        <p role="alert" className="text-sm text-error mt-3">
          {error ?? serverError}
        </p>
      )}
    </Dialog>
  )
}

/** us-037 §4.7 — optional actual cost; warns when the progress is not "Sẵn sàng giao xe" (us-057 AF-1301). */
export function CompleteDialog({
  open,
  plate,
  notReadyForPickup,
  submitting,
  serverError,
  onClose,
  onConfirm,
}: {
  open: boolean
  plate: string
  notReadyForPickup: boolean
  submitting: boolean
  serverError?: string | null
  onClose: () => void
  onConfirm: (actualCost: number | null) => void
}) {
  const [raw, setRaw] = useState('')
  const [error, setError] = useState<string | null>(null)
  const laterRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    setRaw('')
    setError(null)
  }, [open])
  const digits = raw.replace(/\D/g, '')

  function submit() {
    const value = digits ? Number(digits) : null
    if (value !== null && value > 999_999_999) return setError('Chi phí không hợp lệ.')
    setError(null)
    onConfirm(value)
  }

  return (
    <Dialog
      open={open}
      onClose={() => !submitting && onClose()}
      title={`Hoàn tất dịch vụ cho ${plate}?`}
      description="Sau khi hoàn tất: lịch sử bảo dưỡng của xe được cập nhật và khách sẽ nhận lời hỏi thăm sau khoảng 12 giờ."
      initialFocusRef={laterRef}
      dismissable={!submitting}
      className="sm:max-w-md"
      footer={
        <>
          <Button ref={laterRef} variant="secondary" onClick={onClose} disabled={submitting}>
            Để sau
          </Button>
          <Button loading={submitting} loadingText="Đang hoàn tất…" onClick={submit}>
            Hoàn tất
          </Button>
        </>
      }
    >
      {notReadyForPickup && (
        <p className="flex items-start gap-2 text-sm text-warning bg-warning/10 border border-warning/20 rounded-xl px-3 py-2 mb-3">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          Tiến độ chưa ở bước "Sẵn sàng giao xe". Bạn vẫn có thể hoàn tất.
        </p>
      )}
      <TextInput
        label="Chi phí thực tế"
        optional
        inputMode="numeric"
        value={digits ? formatNumber(Number(digits)) : ''}
        onChange={event => setRaw(event.target.value)}
        placeholder="1.850.000"
        aside={<span className="text-xs text-muted">đ</span>}
        error={error ?? serverError ?? undefined}
        disabled={submitting}
      />
    </Dialog>
  )
}
