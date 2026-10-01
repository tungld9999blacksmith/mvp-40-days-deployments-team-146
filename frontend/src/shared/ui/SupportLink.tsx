import { LifeBuoy } from 'lucide-react'
import { SUPPORT_URL } from '@/shared/config/env'
import { cn } from './cn'
import { useToast } from './Toast'

/**
 * "Liên hệ hỗ trợ" / "Liên hệ hãng". The support channel is still an open question in
 * the FE specs; when VITE_SUPPORT_URL is not set the button explains that instead of
 * pretending to open a channel.
 */
export default function SupportLink({
  label = 'Liên hệ hỗ trợ',
  variant = 'secondary',
  className,
}: {
  label?: string
  variant?: 'primary' | 'secondary' | 'ghost'
  className?: string
}) {
  const toast = useToast()
  const style = cn(
    'inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors',
    variant === 'primary' && 'justify-center bg-emerald text-background font-semibold hover:bg-emerald-bright',
    variant === 'secondary' &&
      'justify-center bg-card border border-border text-muted hover:text-foreground hover:bg-card-hover',
    variant === 'ghost' && 'w-full text-muted hover:text-foreground hover:bg-card',
    className,
  )
  if (SUPPORT_URL) {
    return (
      <a href={SUPPORT_URL} target="_blank" rel="noreferrer" className={style}>
        <LifeBuoy className="w-4 h-4" aria-hidden />
        {label}
      </a>
    )
  }
  return (
    <button
      type="button"
      className={style}
      onClick={() => toast.show('Kênh hỗ trợ đang được cập nhật. Vui lòng liên hệ đại lý VinFast gần nhất.', 'info')}
    >
      <LifeBuoy className="w-4 h-4" aria-hidden />
      {label}
    </button>
  )
}
