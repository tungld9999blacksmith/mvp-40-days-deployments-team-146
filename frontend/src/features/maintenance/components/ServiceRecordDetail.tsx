import { Link } from 'react-router-dom'
import { Check, ChevronRight, Gauge, Store, Wallet, Wrench } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { Card } from '@/shared/ui/Card'
import RailRow from '@/shared/ui/RailRow'
import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import type { ServiceRecord } from '@/features/vehicles/types'
import { serviceRecordCost, serviceRecordItems, serviceRecordTitle } from '../utils'

/** Right rail of "Lịch sử dịch vụ" (xl and up): one record in full, with its source and booking. */
export default function ServiceRecordDetail({ record, className }: { record: ServiceRecord; className?: string }) {
  const cost = serviceRecordCost(record)
  const items = serviceRecordItems(record)
  const fromEvCare = record.source === 'EV_CARE'

  return (
    <aside className={className} aria-label="Chi tiết lần dịch vụ">
      <Card className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Badge tone={fromEvCare ? 'success' : 'neutral'}>{fromEvCare ? 'Làm qua EV Care' : 'Đồng bộ từ hãng'}</Badge>
          <span className="font-mono text-xs text-muted">{formatDate(record.serviceDate)}</span>
        </div>
        {/* The note is listed below, so the heading names the kind of visit. */}
        <p className="text-base font-semibold text-foreground">{serviceRecordTitle({ isPeriodic: record.isPeriodic, itemsDone: null })}</p>

        <div>
          <RailRow icon={<Gauge />} label="Số km lúc làm" empty={record.odoKm === null}>
            {record.odoKm !== null ? <span className="font-mono">{formatKm(record.odoKm)}</span> : 'Không có số km'}
          </RailRow>
          <RailRow icon={<Store />} label="Xưởng" empty={!record.workshop}>
            {record.workshop?.name ?? 'Không rõ xưởng'}
          </RailRow>
          <RailRow icon={<Wrench />} label={`Hạng mục đã làm (${items.length})`}>
            <ul className="space-y-1 font-normal">
              {items.map(item => (
                <li key={item} className="flex items-start gap-2 text-[13px]">
                  <Check className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald" aria-hidden />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </RailRow>
          <RailRow icon={<Wallet />} label="Chi phí thực tế" empty={cost === null}>
            {cost !== null ? <span className="font-mono">{formatVnd(cost)}</span> : fromEvCare ? 'Chưa có chi phí cuối' : 'Hãng không gửi chi phí'}
          </RailRow>
        </div>

        {record.bookingId && (
          <Link
            to={`/bookings/${encodeURIComponent(record.bookingId)}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-emerald hover:text-emerald-bright"
          >
            Xem lịch hẹn {record.bookingCode && <span className="font-mono">{record.bookingCode}</span>}
            <ChevronRight className="w-4 h-4" />
          </Link>
        )}
      </Card>
    </aside>
  )
}
