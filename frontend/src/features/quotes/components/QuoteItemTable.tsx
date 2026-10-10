import { ShieldCheck } from 'lucide-react'
import { Card } from '@/shared/ui/Card'
import { formatVnd } from '@/features/estimate/utils'
import type { Quote } from '../types'

/**
 * FE §4.2 (owner) — covered lines show "Bảo hành" and 0 ₫; when the workshop changed a price the
 * estimate is struck through next to the approved price, with the line note.
 */
export default function QuoteItemTable({ quote }: { quote: Quote }) {
  const hasReference = quote.items.some(item => !item.covered && item.priceSource === 'REFERENCE_PRICE')
  return (
    <Card className="p-0 overflow-hidden">
      <ul className="divide-y divide-border">
        {quote.items.map(item => {
          const changed = item.approvedPrice !== null && item.approvedPrice !== item.estimatedPrice
          return (
            <li key={item.quoteItemId} className="px-5 py-3 flex items-start justify-between gap-4 text-sm">
              <div className="min-w-0">
                <p className="text-foreground">
                  {item.itemName}
                  {!item.covered && item.priceSource === 'REFERENCE_PRICE' && (
                    <span className="text-warning" aria-label="giá tham khảo của hãng">
                      {' '}*
                    </span>
                  )}
                </p>
                {item.covered && (
                  <span className="mt-1 inline-flex items-center gap-1 text-xs text-emerald">
                    <ShieldCheck className="w-3.5 h-3.5" /> Bảo hành
                  </span>
                )}
                {item.reviewerNote && <p className="text-xs text-muted mt-1">Xưởng: {item.reviewerNote}</p>}
              </div>
              <div className="text-right whitespace-nowrap font-mono">
                {changed && <p className="text-xs text-muted line-through">{formatVnd(item.estimatedPrice)}</p>}
                <p className="text-foreground">{formatVnd(item.covered ? 0 : item.approvedPrice ?? item.estimatedPrice)}</p>
              </div>
            </li>
          )
        })}
      </ul>
      {hasReference && <p className="px-5 py-2.5 text-xs text-muted border-t border-border">* Giá tham khảo của hãng</p>}
    </Card>
  )
}
