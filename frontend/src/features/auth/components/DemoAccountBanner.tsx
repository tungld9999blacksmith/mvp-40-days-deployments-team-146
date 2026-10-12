import { useEffect, useState } from 'react'
import { Info } from 'lucide-react'
import { formatDemoResetIn } from '../demoAccount'

const TICK_MS = 60_000

/** Strip under the topbar while signed in to the shared demo account ("Dùng thử ngay"). */
export default function DemoAccountBanner({ resetsAt }: { resetsAt?: string | null }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), TICK_MS)
    return () => window.clearInterval(timer)
  }, [])
  const left = formatDemoResetIn(resetsAt, now)

  return (
    <div role="status" className="flex items-start gap-2 px-4 sm:px-6 py-2 bg-emerald/10 border-b border-emerald/20 text-xs text-foreground/80">
      <Info className="w-3.5 h-3.5 mt-px flex-shrink-0 text-emerald" aria-hidden />
      <span>
        Tài khoản dùng thử dùng chung: người khác có thể thấy dữ liệu bạn tạo.{' '}
        {left ? `Dữ liệu tự đặt lại sau ${left}.` : 'Dữ liệu sắp được đặt lại.'}
      </span>
    </div>
  )
}
