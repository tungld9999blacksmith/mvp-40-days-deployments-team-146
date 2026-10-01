/** FEAT-CHAT-001 contract — API Spec us-025 §1.3 and platform conversation-messaging API §1.3. */

export interface CitationDto {
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
  refs: { bookingId?: string; quoteId?: string }
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

export interface ExcerptMessage {
  id: string
  seq: number
  role: 'user' | 'assistant' | string
  content: string
  createdAt: string
}

export interface ConversationExcerpt {
  source: { type: 'booking' | 'quote'; id: string; confirmedMessageId: string }
  messages: ExcerptMessage[]
}
