import EstimateChatCard from '@/features/estimate/components/EstimateChatCard'
import type { ReadyEstimate } from '@/features/estimate/types'
import type { BookingProposalCard as ProposalCard, MessageDto, QuickBookingNeedLocationCard } from '../types'
import BookingProposalCard from './BookingProposalCard'
import RegionPickerCard from './RegionPickerCard'
import DemoBookingProposalCard from './DemoBookingProposalCard'

/**
 * `message.card` (us-025 §Card): F5 estimate (CARD-EST) and the us-061 booking proposal /
 * area picker. Accepts estimate data nested (`card.estimate`) or flat; unknown types render nothing.
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
  return null
}
