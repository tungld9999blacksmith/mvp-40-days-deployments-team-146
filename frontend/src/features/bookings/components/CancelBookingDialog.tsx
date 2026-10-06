import { useEffect, useId, useRef, useState } from 'react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { TextArea } from '@/shared/ui/Field'
import { formatLongDay, slotLabel } from '../utils'

const MAX = 255

/**
 * SCR-702 (us-033 §4.5) — second confirmation before API-BR-03. Focus lands on "Giữ lịch";
 * the reason is kept when a request fails so the owner can retry.
 */
export default function CancelBookingDialog({
  open,
  onClose,
  onConfirm,
  submitting,
  bookingDate,
  timeSlot,
  workshopName,
  fieldError,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (reason: string) => void
  submitting: boolean
  bookingDate: string
  timeSlot: string
  workshopName: string
  fieldError?: string | null
}) {
  const [reason, setReason] = useState('')
  const keepRef = useRef<HTMLButtonElement>(null)
  const noteId = useId()
  useEffect(() => {
    if (open) setReason('')
  }, [open])

  return (
    <Dialog
      open={open}
      onClose={() => !submitting && onClose()}
      role="alertdialog"
      title="Huỷ lịch hẹn?"
      description={
        <>
          {slotLabel(timeSlot)} {formatLongDay(bookingDate)} tại {workshopName}.
          <br />
          <span id={noteId}>Chỗ của bạn sẽ được trả lại cho người khác.</span>
        </>
      }
      initialFocusRef={keepRef}
      dismissable={!submitting}
      footer={
        <>
          <Button ref={keepRef} variant="secondary" onClick={onClose} disabled={submitting}>
            Giữ lịch
          </Button>
          <Button variant="danger" aria-describedby={noteId} loading={submitting} loadingText="Đang huỷ…" onClick={() => onConfirm(reason.trim())}>
            Huỷ lịch
          </Button>
        </>
      }
    >
      <TextArea
        label="Lý do"
        optional
        rows={3}
        maxLength={MAX}
        value={reason}
        disabled={submitting}
        error={fieldError ?? undefined}
        onChange={event => setReason(event.target.value.slice(0, MAX))}
        aside={<span className="text-xs text-muted font-mono">{reason.length}/{MAX}</span>}
      />
    </Dialog>
  )
}
