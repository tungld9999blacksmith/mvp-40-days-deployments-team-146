import { Link } from 'react-router-dom'
import { Calculator, ChevronRight } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import type { ReadyEstimate } from '../types'
import { formatVnd, milestoneLabel } from '../utils'

/**
 * CARD-EST (us-045 §4.7) — `chat_message.card` with the API-EST-02 data: milestone, workshop,
 * at most 3 chargeable lines, the total and "Xem chi tiết" to the same estimate (AC-FE-1004).
 */
export default function EstimateChatCard({ estimate }: { estimate: ReadyEstimate }) {
  const chargeable = estimate.items.filter(item => !item.covered)
  const shown = chargeable.slice(0, 3)
  const detail = `/estimate?odoMilestone=${estimate.milestone.odoMilestone}&workshopId=${encodeURIComponent(estimate.workshop.workshopId)}`
  return (
    <div className="mt-3 rounded-xl border border-emerald/20 bg-background/40 p-3.5 space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <Calculator className="w-3.5 h-3.5 text-emerald" />
          {milestoneLabel(estimate.milestone.odoMilestone, estimate.milestone.monthMilestone)}
        </p>
        <Badge tone="neutral">{estimate.estimateLabel}</Badge>
      </div>
      <p className="text-xs text-muted">{estimate.workshop.name}</p>
      {shown.length > 0 && (
        <ul className="space-y-1 text-xs">
          {shown.map(item => (
            <li key={item.maintenanceRuleId} className="flex justify-between gap-3">
              <span className="text-foreground">
                {item.itemName}
                {item.priceSource === 'REFERENCE_PRICE' ? ' *' : ''}
              </span>
              <span className="font-mono text-muted">{formatVnd(item.price)}</span>
            </li>
          ))}
          {chargeable.length > 3 && <li className="text-muted">và {chargeable.length - 3} mục khác</li>}
        </ul>
      )}
      <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
        <span className="font-mono text-sm font-semibold text-foreground">{formatVnd(estimate.chargeableTotal)}</span>
        <Link to={detail} className="inline-flex items-center gap-1 text-xs font-medium text-emerald hover:text-emerald-bright">
          Xem chi tiết <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}
