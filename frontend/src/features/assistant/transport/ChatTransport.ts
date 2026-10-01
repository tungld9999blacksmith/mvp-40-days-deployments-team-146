import { CHAT_TRANSPORT } from '@/shared/config/env'
import type { ConversationDto, ConversationExcerpt, MessageDto, Paged, SearchResultDto, StreamHandlers } from '../types'
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
  getConversationExcerpt(source: { type: 'booking' | 'quote'; id: string }): Promise<ConversationExcerpt>
}

let instance: ChatTransport | null = null

export function getChatTransport(): ChatTransport {
  if (!instance) instance = CHAT_TRANSPORT === 'http' ? createHttpTransport() : createMockTransport()
  return instance
}
