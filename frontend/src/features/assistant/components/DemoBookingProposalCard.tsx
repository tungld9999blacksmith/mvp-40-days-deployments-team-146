import type { BookingProposalCard as ProposalCard, MessageDto } from '../types'
import BookingProposalCard from './BookingProposalCard'

export function proposalLink(card: NonNullable<MessageDto['card']>): string | null {
  if (card.type !== 'booking_proposal' || typeof card.proposalId !== 'string') return null
  const query = new URLSearchParams({ proposalId: card.proposalId })
  if (typeof card.userVehicleId === 'string') query.set('userVehicleId', card.userVehicleId)
  return `/booking/proposal?${query}`
}

/** Adapt the demo HTTP contract to the branch's proposal component. */
export default function DemoBookingProposalCard({ card }: { card: MessageDto['card'] }) {
  if (!card) return null
  const href = proposalLink(card)
  if (!href) return null
  const vehicle = card.vehicle as ProposalCard['vehicle'] | undefined
  const proposal: ProposalCard = {
    type: 'BOOKING_PROPOSAL', version: 1, proposalId: String(card.proposalId),
    vehicle: { userVehicleId: String(card.userVehicleId), modelName: vehicle?.modelName ?? null, trim: vehicle?.trim ?? null,
      licensePlateMasked: vehicle?.licensePlateMasked ?? null },
    milestone: null, reason: '', locationBasis: 'NONE', locationLabel: null,
    primary: { optionId: String(card.proposalId), workshopId: String(card.workshopId), workshopName: String(card.workshopName),
      address: null, region: null, distanceKm: null, isPreferred: false, date: String(card.date), timeSlot: String(card.timeSlot).slice(0, 5),
      estimate: { chargeableTotal: String(card.estimatedCost), hasReferencePrice: false, coveredCount: 0 } },
    alternatives: [], expiresAt: String(card.expiresAt), status: (card.status as ProposalCard['status']) ?? 'PROPOSED',
    booking: (card.booking as ProposalCard['booking']) ?? null,
  }
  return <BookingProposalCard card={proposal} confirmationHref={href} />
}
