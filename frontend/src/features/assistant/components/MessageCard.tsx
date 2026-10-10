import BookingLinesChatCard, { type BookingLinesCardData } from '@/features/booking-lines/BookingLinesChatCard'
import EstimateChatCard from '@/features/estimate/components/EstimateChatCard'
import type { ReadyEstimate } from '@/features/estimate/types'
import QuoteChatCard from '@/features/quotes/components/QuoteChatCard'
import type { Quote } from '@/features/quotes/types'
import type { BookingProposalCard as ProposalCard, MessageDto, QuickBookingNeedLocationCard } from '../types'
import BookingProposalCard from './BookingProposalCard'
import RegionPickerCard from './RegionPickerCard'
import DemoBookingProposalCard from './DemoBookingProposalCard'

/**
 * `message.card` (us-025 §Card): F5 estimate (CARD-EST), F5b quote (CARD-QUOTE), the two-tier
 * price lines (BOOKING_LINES, bao-gia-hai-tang 3A) and the us-061
 * booking proposal / area picker. Accepts estimate and quote data nested (`card.estimate` /
 * `card.quote`) or flat; unknown types render nothing.
 */
export default function MessageCard({ card }: { card: MessageDto['card'] }) {
  if (!card) return null
  if (card.type.toUpperCase() === 'BOOKING_PROPOSAL' && !card.primary) return <DemoBookingProposalCard card={card} />
  if (card.type === 'BOOKING_PROPOSAL') return <BookingProposalCard card={card as unknown as ProposalCard} />
  if (card.type === 'QUICK_BOOKING_NEED_LOCATION') return <RegionPickerCard card={card as unknown as QuickBookingNeedLocationCard} />
  const type = card.type.toUpperCase().replace(/^CARD[-_]/, '')
  if (type === 'ESTIMATE' || type === 'EST') {
    const estimate = (card.estimate ?? card) as ReadyEstimate
    return estimate.status === 'READY' ? <EstimateChatCard estimate={estimate} /> : null
  }
  if (type === 'BOOKING_LINES') {
    const lines = card as unknown as BookingLinesCardData
    return lines.bookingId ? <BookingLinesChatCard card={lines} /> : null
  }
  if (type === 'QUOTE') {
    const quote = (card.quote ?? card) as Quote
    return quote.quoteId ? <QuoteChatCard quote={quote} /> : null
  }
  return null
}
