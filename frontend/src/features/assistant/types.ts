/** FEAT-CHAT-001 contract — API Spec us-025 §1.3 and platform conversation-messaging API §1.3. */

export interface CitationDto {
  sourceUrl?: string
  title: string
  version: string
  documentType: 'owner_manual' | 'maintenance_manual' | 'warranty_policy' | 'service_bulletin' | string
  pageNumber: number | null
  snippet: string
}

export interface MessageDto {
  id: string
  seq: number
  role: 'user' | 'assistant' | string
  content: string
  citations: CitationDto[]
  /** `inReplyTo`: the owner message a quick-booking answer belongs to (us-061 API §4.2). */
  refs: { bookingId?: string; inReplyTo?: string }
  /** Structured UI card for F5/F6 — rendered by those specs. */
  card: { type: string; [key: string]: unknown } | null
  createdAt: string
}

export interface ConversationDto {
  id: string
  userVehicleId: string
  title: string | null
  lastMessageAt: string
  createdAt: string
  lastMessagePreview?: string | null
}

export interface SearchResultDto {
  conversationId: string
  conversationTitle: string | null
  messageId: string
  seq: number
  role: 'user' | 'assistant' | string
  /** ≤ 200 chars, matches wrapped in <mark>, other HTML escaped by the backend. */
  snippet: string
  createdAt: string
}

export interface Paged<T> {
  data: T[]
  page: { nextCursor: string | null; hasMore: boolean }
}

export type StreamStage = 'retrieving' | 'calling_tool' | 'generating' | (string & {})

export interface StreamErrorPayload {
  code: 'AGENT_FAILED' | 'AGENT_TIMEOUT' | 'LLM_UNAVAILABLE' | string
  message: string
  traceId?: string | null
}

export interface StreamHandlers {
  onAccepted: (userMessage: MessageDto, replayed: boolean) => void
  onStatus: (stage: StreamStage, tool?: string) => void
  onToken: (delta: string) => void
  onCompleted: (message: MessageDto) => void
  onError: (error: StreamErrorPayload) => void
}

/** us-061 API §3.2 — a quick-booking option (main or alternative). */
export interface ProposalOption {
  optionId: string
  workshopId: string
  workshopName: string
  address: string | null
  region: string | null
  /** Only from real coordinates; `null` when ranked by area (BR-1506). */
  distanceKm: number | null
  isPreferred: boolean
  date: string
  timeSlot: string
  estimate: { chargeableTotal: string; hasReferencePrice: boolean; coveredCount: number } | null
}

export interface ProposalMilestone {
  odoMilestoneKm: number
  monthMilestone: number
  label: string
  dueDate: string
  dueStatus: string
  dueReason: string | null
  remainingKm: number | null
  remainingDays: number | null
  items: { itemCode: string; itemName: string; isCoveredByWarranty: boolean }[]
}

export type ProposalStatus = 'PROPOSED' | 'CONFIRMED' | 'CANCELLED' | 'SUPERSEDED' | 'EXPIRED'

export interface ProposalBooking {
  bookingId: string
  /** Only once the booking is confirmed (never while PENDING). */
  bookingCode: string | null
  status: string
  ownerCancelableUntil: string | null
}

export interface BookingProposalCard {
  type: 'BOOKING_PROPOSAL'
  version: number
  proposalId: string
  vehicle: { userVehicleId: string; modelName: string | null; trim: string | null; licensePlateMasked: string | null }
  milestone: ProposalMilestone | null
  reason: string
  locationBasis: 'DEVICE' | 'PROFILE' | 'PROVINCE' | 'NONE'
  locationLabel: string | null
  primary: ProposalOption
  alternatives: ProposalOption[]
  expiresAt: string
  /** Live, added by the backend on every read (HOOK-QB-01). */
  status: ProposalStatus
  booking: ProposalBooking | null
}

export interface QuickBookingNeedLocationCard {
  type: 'QUICK_BOOKING_NEED_LOCATION'
  version: number
  regions: string[]
}

export interface ConfirmProposalResult {
  proposalId: string
  status: 'CONFIRMED'
  booking: {
    bookingId: string
    bookingCode: string | null
    status: string
    confirmationMode: string | null
    workshopName: string | null
    bookingDate: string
    timeSlot: string
    ownerCancelableUntil: string | null
  }
  message: MessageDto | null
  replayed: boolean
}

export interface ExcerptMessage {
  id: string
  seq: number
  role: 'user' | 'assistant' | string
  content: string
  createdAt: string
}

export interface ConversationExcerpt {
  source: { type: 'booking'; id: string; confirmedMessageId: string }
  messages: ExcerptMessage[]
}
