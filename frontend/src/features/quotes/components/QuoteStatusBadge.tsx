import Badge, { type BadgeTone } from '@/shared/ui/Badge'
import type { QuoteDisplayStatus } from '../types'

/** FE §4.1 */
export const QUOTE_STATUS: Record<QuoteDisplayStatus, { label: string; tone: BadgeTone }> = {
  DRAFT: { label: 'Nháp', tone: 'neutral' },
  PENDING_APPROVAL: { label: 'Chờ xưởng duyệt', tone: 'warning' },
  APPROVED: { label: 'Đã duyệt', tone: 'success' },
  MODIFIED: { label: 'Đã duyệt (có điều chỉnh)', tone: 'success' },
  EXPIRED: { label: 'Hết hiệu lực', tone: 'neutral' },
  REJECTED: { label: 'Bị từ chối', tone: 'error' },
}

export default function QuoteStatusBadge({ status, className }: { status: QuoteDisplayStatus; className?: string }) {
  const { label, tone } = QUOTE_STATUS[status] ?? { label: status, tone: 'neutral' as const }
  return (
    <Badge tone={tone} className={className}>
      {label}
    </Badge>
  )
}
