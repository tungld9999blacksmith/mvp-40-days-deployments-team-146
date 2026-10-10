import { Link } from 'react-router-dom'
import { ChevronRight, ReceiptText, ShieldAlert } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { formatVnd } from '@/features/estimate/utils'

export interface BookingLinesCardData {
  type: 'BOOKING_LINES'
  bookingId: string
  bookingCode: string
  bookingStatus: string
  pendingCount: number
  pendingItems: { lineId: string; kind: string; itemName: string; price: number; isSafetyCritical: boolean }[]
  currentTotal: number
  totalIfAllApproved: number
}

/**
 * Design 3A — chat summary of the price lines. No decision buttons here: the
 * booking ticket is the only place where the owner approves or declines.
 */
export default function BookingLinesChatCard({ card }: { card: BookingLinesCardData }) {
  const ticket = `/bookings/${encodeURIComponent(card.bookingId)}`
  const waiting = card.pendingCount > 0
  return (
    <div className="mt-3 rounded-xl border border-emerald/20 bg-background/40 p-3.5 space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <ReceiptText className="w-3.5 h-3.5 text-emerald" aria-hidden />
          Giá lịch hẹn <span className="font-mono font-normal text-muted">{card.bookingCode}</span>
        </p>
        {waiting ? <Badge tone="warning">{card.pendingCount} chờ bạn</Badge> : <Badge tone="success">Đã chốt</Badge>}
      </div>
      {waiting && (
        <ul className="divide-y divide-border">
          {card.pendingItems.map(item => (
            <li key={item.lineId} className="flex items-center justify-between gap-3 py-1.5 text-xs">
              <span className="text-foreground inline-flex items-center gap-1 min-w-0">
                {item.isSafetyCritical && <ShieldAlert className="w-3.5 h-3.5 text-warning shrink-0" aria-label="Hạng mục an toàn" />}
                <span className="truncate">{item.itemName}</span>
              </span>
              <span className="font-mono text-foreground whitespace-nowrap">{formatVnd(item.price)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
        <span className="text-xs text-muted">
          {waiting ? 'Nếu đồng ý hết' : 'Tổng'}{' '}
          <span className="font-mono text-sm font-semibold text-foreground">{formatVnd(waiting ? card.totalIfAllApproved : card.currentTotal)}</span>
        </span>
        <Link to={ticket} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald hover:text-emerald-bright">
          {waiting ? 'Mở phiếu để quyết định' : 'Xem phiếu'} <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}
