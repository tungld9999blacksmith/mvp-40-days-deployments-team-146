import { createContext, useContext } from 'react'

/** Result of a card action: errors are shown inside the card (FE spec §3). */
export type ProposalOutcome = { ok: true } | { ok: false; message: string; bookingId?: string | null; retryable?: boolean }

export interface ReviseChoice {
  workshopId: string
  date: string
  timeSlot: string
}

/** Card actions of us-061, provided by the chat screen so cards deep in the message list can act. */
export interface QuickBookingActions {
  /** API-QB-01 again (expired card, region picker). */
  start: (options?: { province?: string | null }) => Promise<void>
  /** API-QB-02 — the only way a proposal becomes a booking. */
  confirm: (proposalId: string) => Promise<ProposalOutcome>
  /** API-QB-03 */
  revise: (proposalId: string, choice: ReviseChoice) => Promise<ProposalOutcome>
  /** API-QB-04 */
  cancel: (proposalId: string) => Promise<ProposalOutcome>
  /** A quick-booking request or a chat turn is running: card actions wait meanwhile. */
  busy: boolean
}

const QuickBookingContext = createContext<QuickBookingActions | null>(null)

export const QuickBookingProvider = QuickBookingContext.Provider

/** `null` outside the chat screen: cards then show no actions. */
export function useQuickBookingActions(): QuickBookingActions | null {
  return useContext(QuickBookingContext)
}
