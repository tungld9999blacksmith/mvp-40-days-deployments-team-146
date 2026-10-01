import { useRef, useState } from 'react'
import Dialog from '@/shared/ui/Dialog'
import Button from '@/shared/ui/Button'

/** SCR-104 / SCR-304 — confirm before logging out. */
export default function LogoutConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = 'Đăng xuất khỏi EV Care?',
  description = 'Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục. Các thiết bị khác đang đăng nhập cùng tài khoản cũng sẽ phải đăng nhập lại.',
  note,
}: {
  open: boolean
  onClose: () => void
  onConfirm: () => Promise<unknown>
  title?: string
  description?: string
  note?: string
}) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const [pending, setPending] = useState(false)

  async function confirm() {
    setPending(true)
    try {
      await onConfirm()
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      role="alertdialog"
      title={title}
      description={description}
      initialFocusRef={cancelRef}
      dismissable={!pending}
      footer={
        <>
          <Button ref={cancelRef} variant="secondary" onClick={onClose} disabled={pending}>
            Huỷ
          </Button>
          <Button variant="danger" onClick={() => void confirm()} loading={pending}>
            Đăng xuất
          </Button>
        </>
      }
    >
      {note && <p className="text-xs text-muted leading-relaxed">{note}</p>}
    </Dialog>
  )
}
