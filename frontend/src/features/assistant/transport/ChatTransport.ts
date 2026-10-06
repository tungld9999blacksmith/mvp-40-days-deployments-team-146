import { CHAT_TRANSPORT } from '@/shared/config/env'
import type {
  ConfirmProposalResult,
  ConversationDto,
  ConversationExcerpt,
  MessageDto,
  Paged,
  SearchResultDto,
  StreamHandlers,
} from '../types'
import { createHttpTransport } from './httpTransport'
import { createMockTransport } from './mockTransport'

/**
 * Chat backend contract (API Spec us-025 + platform conversation-messaging).
 * `http` talks to the backend; `mock` simulates the same contract until the backend
 * replaces its PROVISIONAL conversation routes (prompt rule 8, VITE_CHAT_TRANSPORT).
 */
export interface ChatTransport {
  readonly kind: 'http' | 'mock'
  /** API-CONV-002 — newest first. */
  listConversations(params: { userVehicleId?: string; limit: number; cursor?: string | null }): Promise<Paged<ConversationDto>>
  /** API-CONV-001 */
  createConversation(userVehicleId: string): Promise<ConversationDto>
  /** API-CONV-003 — `before` → newest first; `after` → ascending. */
  getMessages(
    conversationId: string,
    params: { limit: number; before?: number; after?: number },
  ): Promise<Paged<MessageDto>>
  /**
   * API-CHAT-004 — resolves when the stream ends with `message.completed` or `error`.
   * Throws `ApiError` for pre-stream errors (JSON 4xx/5xx) and when the stream breaks.
   */
  sendMessage(
    conversationId: string,
    body: { clientMessageId: string; content: string },
    handlers: StreamHandlers,
    signal: AbortSignal,
  ): Promise<void>
  /** API-CONV-004 */
  searchMessages(params: { q: string; userVehicleId?: string; limit: number; cursor?: string | null }): Promise<Paged<SearchResultDto>>
  /** API-CONV-005 — 204 */
  deleteConversation(conversationId: string): Promise<void>
  /** API-CHAT-007 / API-CHAT-008 (Workshop Portal). */
  getConversationExcerpt(source: { type: 'booking'; id: string }): Promise<ConversationExcerpt>
  /** us-061 API-QB-01 — the quick-booking chip: a proposal card, never a booking. */
  quickBooking(
    conversationId: string,
    body: { clientMessageId: string; location: { lat: number; lng: number } | null; province: string | null },
  ): Promise<{ userMessage: MessageDto; assistantMessage: MessageDto; replayed: boolean }>
  /** us-061 API-QB-02 — the only way a proposal becomes a booking. Idempotent per proposal. */
  confirmProposal(conversationId: string, proposalId: string): Promise<ConfirmProposalResult>
  /** us-061 API-QB-03 */
  reviseProposal(
    conversationId: string,
    proposalId: string,
    body: { workshopId: string; date: string; timeSlot: string },
  ): Promise<{ proposalId: string; message: MessageDto }>
  /** us-061 API-QB-04 */
  cancelProposal(conversationId: string, proposalId: string): Promise<{ proposalId: string; status: 'CANCELLED' }>
}

let instance: ChatTransport | null = null

export function getChatTransport(): ChatTransport {
  if (!instance) instance = CHAT_TRANSPORT === 'http' ? createHttpTransport() : createMockTransport()
  return instance
}
