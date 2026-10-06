import { ShieldCheck } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import { Card } from '@/shared/ui/Card'
import type { ReadyEstimate } from '../types'
import { formatVnd } from '../utils'

/** FE §4.3 — two groups by `covered`; `*` marks a reference price. */
export function EstimateItemList({ estimate }: { estimate: ReadyEstimate }) {
  const covered = estimate.items.filter(item => item.covered)
  const chargeable = estimate.items.filter(item => !item.covered)
  const showCovered = covered.length > 0 && estimate.coveredCount > 0 && estimate.warrantyStatus !== 'EXPIRED'

  return (
    <Card className="p-0 overflow-hidden">
      {showCovered && (
        <section aria-label="Trong bảo hành" className="px-5 py-4 border-b border-border">
          <p className="text-[13px] font-semibold text-emerald flex items-center gap-1.5 mb-2">
            <ShieldCheck className="w-4 h-4" aria-hidden />
            Trong bảo hành (miễn phí)
          </p>
          <ul className="divide-y divide-border">
            {covered.map(item => (
              <li key={item.maintenanceRuleId} className="flex items-center justify-between gap-4 py-2.5 text-sm">
                <span className="text-foreground">{item.itemName}</span>
                <span className="text-emerald font-medium">Miễn phí</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-label="Tính phí" className="px-5 py-4">
        <p className="text-[13px] font-semibold text-muted mb-2">Tính phí</p>
        {chargeable.length === 0 ? (
          <p className="text-sm text-muted py-2">Không có hạng mục tính phí.</p>
        ) : (
          <ul className="divide-y divide-border">
            {chargeable.map(item => (
              <li key={item.maintenanceRuleId} className="flex items-center justify-between gap-4 py-2.5 text-sm">
                <span className="text-foreground">
                  {item.itemName}
                  {item.priceSource === 'REFERENCE_PRICE' && (
                    <span className="text-warning" aria-label="giá tham khảo của hãng">
                      {' '}*
                    </span>
                  )}
                </span>
                <span className="font-mono text-foreground whitespace-nowrap">{formatVnd(item.price)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Card>
  )
}

/** FE §4.4 — total from `chargeableTotal`, the fixed "Chi phí ước tính" label and notes. */
export function EstimateTotal({ estimate }: { estimate: ReadyEstimate }) {
  const free = estimate.chargeableTotal === 0
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted">Tổng chi phí ước tính</p>
          {free ? (
            <p className="text-base font-semibold text-foreground mt-1">Mốc này không phát sinh chi phí theo định mức</p>
          ) : (
            <p className="text-3xl font-bold tracking-tight text-foreground mt-1 font-mono" aria-label={`${formatVnd(estimate.chargeableTotal)} đồng`}>
              {formatVnd(estimate.chargeableTotal)}
            </p>
          )}
        </div>
        <Badge tone="neutral">{estimate.estimateLabel}</Badge>
      </div>
      <p className="text-xs text-muted leading-relaxed">
        Chi phí thực tế có thể thay đổi tuỳ tình trạng xe khi kiểm tra tại xưởng. Dự toán chỉ để tham khảo, chi phí cuối cùng do xưởng xác nhận.
      </p>
      {estimate.hasReferencePrice && <p className="text-xs text-muted">* Giá tham khảo của hãng (xưởng chưa có giá riêng cho hạng mục này).</p>}
      {estimate.warrantyStatus === 'EXPIRED' && <p className="text-xs text-warning">Xe đã hết thời hạn bảo hành chung — mọi hạng mục đều tính phí.</p>}
      {estimate.warrantyStatus === 'UNKNOWN' && <p className="text-xs text-muted">Chưa có dữ liệu bảo hành từ hãng.</p>}
    </Card>
  )
}
