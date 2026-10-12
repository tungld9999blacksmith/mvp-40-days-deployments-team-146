import { useEffect, useState } from 'react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { TextInput } from '@/shared/ui/Field'
import { cn } from '@/shared/ui/cn'
import { formatVnd } from '@/features/estimate/utils'
import { PHONE_NAME_MAX, phoneNameError } from '@/features/booking-lines/logic'
import type { BookingLine, Decision } from '@/features/booking-lines/types'

/**
 * TODOS P2 (concern R2-2) — the owner answered by phone. The workshop records the answer
 * and who gave it; the owner is told at once and can dispute it until the car is completed.
 */
export default function PhoneDecisionDialog({
  line,
  busy,
  onClose,
  onSubmit,
}: {
  line: BookingLine | null
  busy: boolean
  onClose: () => void
  onSubmit: (body: { decision: Decision; confirmedByName: string; confirmSafety: boolean }) => void
}) {
  const [decision, setDecision] = useState<Decision | null>(null)
  const [name, setName] = useState('')
  const [touched, setTouched] = useState(false)
  const [safetyOk, setSafetyOk] = useState(false)

  useEffect(() => {
    setDecision(null)
    setName('')
    setTouched(false)
    setSafetyOk(false)
  }, [line?.lineId])

  const nameError = phoneNameError(name)
  const needsSafety = Boolean(line?.isSafetyCritical) && decision === 'DECLINE'
  const ready = decision !== null && !nameError && (!needsSafety || safetyOk)

  const choice = (value: Decision, label: string) => (
    <button
      type="button"
      role="radio"
      aria-checked={decision === value}
      onClick={() => setDecision(value)}
      className={cn(
        'flex-1 rounded-xl border px-3 py-2.5 text-sm font-medium transition-colors',
        decision === value ? 'border-emerald bg-emerald-dim text-emerald' : 'border-border text-foreground hover:bg-card-hover',
      )}
    >
      {label}
    </button>
  )

  return (
    <Dialog
      open={line !== null}
      onClose={() => !busy && onClose()}
      dismissable={!busy}
      title={line ? `Ghi quyết định qua điện thoại · ${line.itemName}` : ''}
      description={line ? `${formatVnd(line.price)}. Chủ xe nhận thông báo ngay và có thể bấm "Tôi không đồng ý" trước khi hoàn tất.` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Huỷ
          </Button>
          <Button
            loading={busy}
            loadingText="Đang lưu…"
            disabled={!ready}
            onClick={() => {
              setTouched(true)
              if (ready && decision) onSubmit({ decision, confirmedByName: name.trim(), confirmSafety: needsSafety && safetyOk })
            }}
          >
            Lưu quyết định
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div role="radiogroup" aria-label="Chủ xe trả lời" className="flex gap-2">
          {choice('APPROVE', 'Đồng ý làm')}
          {choice('DECLINE', 'Không làm')}
        </div>
        <TextInput
          label="Người xác nhận qua điện thoại"
          placeholder="Ví dụ: Anh Trung (chủ xe)"
          maxLength={PHONE_NAME_MAX}
          value={name}
          onChange={event => setName(event.target.value)}
          onBlur={() => setTouched(true)}
          error={touched ? (nameError ?? undefined) : undefined}
        />
        {needsSafety && (
          <label className="flex items-start gap-2 text-sm text-foreground">
            <input type="checkbox" className="mt-0.5" checked={safetyOk} onChange={event => setSafetyOk(event.target.checked)} />
            Đã nói rõ với chủ xe đây là hạng mục an toàn (phanh, lốp, lái hoặc đèn) và chủ xe vẫn không làm.
          </label>
        )}
      </div>
    </Dialog>
  )
}
