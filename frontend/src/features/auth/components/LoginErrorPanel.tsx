import { AlertTriangle } from 'lucide-react'
import Button from '@/shared/ui/Button'
import SupportLink from '@/shared/ui/SupportLink'

/** SCR-103 / SCR-303 — account locked or sign-in refused by the backend. */
export default function LoginErrorPanel({
  title,
  message,
  supportLabel = 'Liên hệ hỗ trợ',
  onOtherAccount,
}: {
  title: string
  message: string
  supportLabel?: string
  onOtherAccount: () => void
}) {
  return (
    <div role="alert" className="bg-card border border-border rounded-2xl p-6 elevation-sm">
      <div className="w-10 h-10 rounded-xl bg-error/10 flex items-center justify-center mb-4">
        <AlertTriangle className="w-5 h-5 text-error" aria-hidden />
      </div>
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      <p className="text-sm text-muted mt-2 leading-relaxed">{message}</p>
      <div className="mt-6 flex flex-col gap-2">
        <SupportLink label={supportLabel} variant="primary" />
        <Button variant="secondary" fullWidth onClick={onOtherAccount}>
          Đăng nhập bằng tài khoản khác
        </Button>
      </div>
    </div>
  )
}
