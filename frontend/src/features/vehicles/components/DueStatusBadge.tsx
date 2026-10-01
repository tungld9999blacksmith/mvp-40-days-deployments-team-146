import { AlertOctagon, AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react'
import Badge, { type BadgeTone } from '@/shared/ui/Badge'

const STATUS: Record<string, { label: string; tone: BadgeTone; Icon: typeof CheckCircle2 }> = {
  NORMAL: { label: 'Bình thường', tone: 'success', Icon: CheckCircle2 },
  DUE_SOON: { label: 'Sắp đến hạn', tone: 'warning', Icon: AlertTriangle },
  OVERDUE: { label: 'Quá hạn', tone: 'error', Icon: AlertOctagon },
  UNKNOWN: { label: 'Chưa xác định', tone: 'neutral', Icon: HelpCircle },
}

/** Tone used for the progress bar / emphasized text of a due status. */
export function dueTone(status: string): BadgeTone {
  return (STATUS[status] ?? STATUS.UNKNOWN).tone
}

/** Maintenance due badge in Vietnamese; unknown enum values fall back to "Chưa xác định". */
export default function DueStatusBadge({ status }: { status: string }) {
  const { label, tone, Icon } = STATUS[status] ?? STATUS.UNKNOWN
  return (
    <Badge tone={tone} icon={<Icon className="w-3.5 h-3.5" aria-hidden />}>
      {label}
    </Badge>
  )
}
