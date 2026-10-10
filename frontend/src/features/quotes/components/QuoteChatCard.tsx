import { Link } from 'react-router-dom'
import { ChevronRight, FileText, Send } from 'lucide-react'
import { formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import type { Quote } from '../types'
import QuoteStatusBadge from './QuoteStatusBadge'

/**
 * CARD-QUOTE (us-049 §4.5). A draft is only sent after the owner's explicit confirmation
 * (BR-1103): until the chat confirmation-event contract exists (us-025 Q-FE-CHAT-03) the button
 * opens the quote, where "Gửi xưởng duyệt" asks for that confirmation.
 */
export default function QuoteChatCard({ quote }: { quote: Quote }) {
  const detail = `/quotes/${encodeURIComponent(quote.quoteId)}`
  const total = quote.approvedTotal ?? quote.estimatedTotal
  return (
    <div className="mt-3 rounded-xl border border-emerald/20 bg-background/40 p-3.5 space-y-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-emerald" />
          Báo giá · mốc {formatKm(quote.odoMilestone)}
        </p>
        <QuoteStatusBadge status={quote.displayStatus} />
      </div>
      <p className="text-xs text-muted">{quote.workshop.name}</p>
      <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
        <span className="font-mono text-sm font-semibold text-foreground">{formatVnd(total)}</span>
        {quote.displayStatus === 'DRAFT' ? (
          <Link to={detail} className="inline-flex items-center gap-1 text-xs font-semibold text-emerald hover:text-emerald-bright">
            <Send className="w-3.5 h-3.5" /> Gửi xưởng duyệt
          </Link>
        ) : (
          <Link to={detail} className="inline-flex items-center gap-1 text-xs font-medium text-emerald hover:text-emerald-bright">
            Xem chi tiết <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        )}
      </div>
    </div>
  )
}
