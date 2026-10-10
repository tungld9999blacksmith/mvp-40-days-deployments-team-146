import { ClipboardList, ShieldAlert, ShieldCheck } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { Card, CardHeader } from '@/shared/ui/Card'
import { formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import { OWNER_LINE_STATUS } from '@/features/booking-lines/logic'
import type { BookingLine, LinesView } from '@/features/booking-lines/types'

function PriceLabel({ line }: { line: BookingLine }) {
  if (line.isCoveredByWarranty)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald">
        <ShieldCheck className="w-3.5 h-3.5" aria-hidden /> Bảo hành
      </span>
    )
  if (line.status === 'PENDING_CONFIRM') return <span className="text-xs text-warning">Giá tham khảo, xưởng xác nhận khi nhận xe</span>
  return <span className="text-xs text-muted">{line.priceLabel}</span>
}

function Row({ line }: { line: BookingLine }) {
  const status = OWNER_LINE_STATUS[line.status]
  const struck = line.status === 'DECLINED' || line.status === 'WITHDRAWN'
  const showStatus = line.status !== 'CONFIRMED' && line.status !== 'PENDING_CONFIRM'
  return (
    <li className="flex items-start justify-between gap-3 py-2.5 text-sm">
      <span className="min-w-0">
        <span className={struck ? 'text-muted line-through' : 'text-foreground'}>{line.itemName}</span>
        <span className="flex flex-wrap items-center gap-2 mt-0.5">
          <PriceLabel line={line} />
          {line.isSafetyCritical && line.kind === 'EXTRA' && <ShieldAlert className="w-3.5 h-3.5 text-warning" aria-label="Hạng mục an toàn" />}
          {showStatus && <Badge tone={status.tone}>{status.label}</Badge>}
        </span>
      </span>
      <span className={`font-mono whitespace-nowrap ${struck ? 'text-muted line-through' : 'text-foreground'}`}>
        {line.isCoveredByWarranty ? 'Miễn phí' : formatVnd(line.price)}
      </span>
    </li>
  )
}

/**
 * Design 1A — the "Hạng mục" card of a two-tier booking becomes the full price
 * list: package lines (with "Giá xưởng" / "Giá tham khảo" / "Bảo hành"), extras
 * and each line's state, then the settled total.
 */
export default function PriceLinesCard({ view, odoMilestone }: { view: LinesView; odoMilestone: number | null }) {
  const pkg = view.lines.filter(line => line.kind === 'PACKAGE')
  const extras = view.lines.filter(line => line.kind === 'EXTRA')
  const waiting = view.pendingDecisionCount > 0 || view.unconfirmedCount > 0
  return (
    <Card>
      <CardHeader
        title={odoMilestone ? `Hạng mục · mốc ${formatKm(odoMilestone)}` : 'Hạng mục'}
        icon={<ClipboardList className="w-4 h-4 text-muted" />}
      />
      {view.packageNotice && pkg.length === 0 && <p className="text-sm text-muted">{view.packageNotice}.</p>}
      {pkg.length > 0 && (
        <section aria-label="Gói bảo dưỡng">
          <p className="text-[13px] font-semibold text-muted">Gói bảo dưỡng</p>
          <ul className="divide-y divide-border">
            {pkg.map(line => (
              <Row key={line.lineId} line={line} />
            ))}
          </ul>
        </section>
      )}
      {extras.length > 0 && (
        <section aria-label="Phát sinh" className="mt-3">
          <p className="text-[13px] font-semibold text-muted">Phát sinh</p>
          <ul className="divide-y divide-border">
            {extras.map(line => (
              <Row key={line.lineId} line={line} />
            ))}
          </ul>
        </section>
      )}
      <div className="mt-4 pt-3 border-t border-border space-y-1 text-sm">
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted">{waiting ? 'Đã chốt' : 'Tổng'}</span>
          <span className="font-mono text-foreground font-semibold">{formatVnd(view.currentTotal)}</span>
        </div>
        {waiting && view.totalIfAllApproved !== view.currentTotal && (
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted">Nếu đồng ý hết</span>
            <span className="font-mono text-muted">{formatVnd(view.totalIfAllApproved)}</span>
          </div>
        )}
      </div>
    </Card>
  )
}
