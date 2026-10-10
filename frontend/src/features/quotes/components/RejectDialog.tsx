import { useEffect, useState } from 'react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { TextArea } from '@/shared/ui/Field'

const MIN = 10
const MAX = 500

/** SCR-1113 — reason required, 10–500 characters (BR-1107); shown verbatim to the owner. */
export default function RejectDialog({
  open,
  onClose,
  onConfirm,
  submitting,
  serverError,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (reason: string) => void
  submitting: boolean
  serverError?: string | null
}) {
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) setReason('')
  }, [open])
  const length = reason.trim().length
  const valid = length >= MIN && length <= MAX

  return (
    <Dialog
      open={open}
      onClose={() => !submitting && onClose()}
      role="alertdialog"
      title="Từ chối báo giá"
      description="Khách sẽ đọc được nguyên văn lý do này."
      dismissable={!submitting}
      className="sm:max-w-md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Huỷ
          </Button>
          <Button variant="danger" disabled={!valid} loading={submitting} loadingText="Đang gửi…" onClick={() => onConfirm(reason.trim())}>
            Từ chối
          </Button>
        </>
      }
    >
      <TextArea
        label="Lý do từ chối"
        required
        rows={4}
        maxLength={MAX}
        value={reason}
        onChange={event => setReason(event.target.value)}
        aside={<span className="text-xs text-muted font-mono">{reason.length}/{MAX}</span>}
        helper={length > 0 && length < MIN ? `Tối thiểu ${MIN} ký tự.` : undefined}
        error={serverError ?? undefined}
        disabled={submitting}
      />
    </Dialog>
  )
}
