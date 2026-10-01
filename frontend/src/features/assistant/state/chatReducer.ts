import type { ApiError } from '@/shared/api/client'
import type { MessageDto, StreamStage } from '../types'

/**
 * Merges messages from any source (history pages, SSE, WebSocket): sorted by `seq`,
 * de-duplicated by `id` (the newer copy wins). Only user/assistant roles are kept.
 */
export function mergeMessages(existing: MessageDto[], incoming: MessageDto[]): MessageDto[] {
  const byId = new Map<string, MessageDto>()
  for (const message of existing) byId.set(message.id, message)
  for (const message of incoming) {
    if (message.role !== 'user' && message.role !== 'assistant') continue
    byId.set(message.id, message)
  }
  return [...byId.values()].sort((a, b) => a.seq - b.seq)
}

/** A user message sent from this device that has no saved answer yet. */
export interface PendingUserMessage {
  clientMessageId: string
  content: string
  /** Server id once `message.accepted` arrived. */
  messageId: string | null
  status: 'sending' | 'failed' | 'unanswered'
  /** Helper text shown under the bubble. */
  note: string | null
}

export interface StreamingState {
  clientMessageId: string
  draft: string
  stage: StreamStage | null
}

export interface ChatState {
  conversationId: string | null
  title: string | null
  messages: MessageDto[]
  olderCursor: string | null
  hasOlder: boolean
  loadingOlder: boolean
  loading: boolean
  loadError: ApiError | null
  pending: PendingUserMessage[]
  streaming: StreamingState | null
  highlightSeq: number | null
}

export const initialChatState: ChatState = {
  conversationId: null,
  title: null,
  messages: [],
  olderCursor: null,
  hasOlder: false,
  loadingOlder: false,
  loading: false,
  loadError: null,
  pending: [],
  streaming: null,
  highlightSeq: null,
}

export type ChatAction =
  | { type: 'reset'; conversationId: string | null; title: string | null; loading: boolean }
  | { type: 'loaded'; messages: MessageDto[]; olderCursor: string | null; hasOlder: boolean; highlightSeq?: number | null }
  | { type: 'load-failed'; error: ApiError }
  | { type: 'older-start' }
  | { type: 'older-loaded'; messages: MessageDto[]; olderCursor: string | null; hasOlder: boolean }
  | { type: 'older-failed' }
  | { type: 'merge'; messages: MessageDto[] }
  | { type: 'conversation-created'; conversationId: string; title: string | null }
  | { type: 'send'; clientMessageId: string; content: string }
  | { type: 'accepted'; clientMessageId: string; message: MessageDto }
  | { type: 'stage'; stage: StreamStage }
  | { type: 'token'; delta: string }
  | { type: 'completed'; clientMessageId: string; message: MessageDto }
  | { type: 'turn-failed'; clientMessageId: string; status: 'failed' | 'unanswered'; note: string | null }
  | { type: 'drop-pending'; clientMessageId: string }
  | { type: 'set-title'; title: string | null }
  | { type: 'clear-highlight' }

function updatePending(state: ChatState, clientMessageId: string, change: Partial<PendingUserMessage>): PendingUserMessage[] {
  return state.pending.map(item => (item.clientMessageId === clientMessageId ? { ...item, ...change } : item))
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'reset':
      return { ...initialChatState, conversationId: action.conversationId, title: action.title, loading: action.loading }
    case 'loaded':
      return {
        ...state,
        loading: false,
        loadError: null,
        messages: mergeMessages([], action.messages),
        olderCursor: action.olderCursor,
        hasOlder: action.hasOlder,
        highlightSeq: action.highlightSeq ?? null,
      }
    case 'load-failed':
      return { ...state, loading: false, loadError: action.error }
    case 'older-start':
      return { ...state, loadingOlder: true }
    case 'older-loaded':
      return {
        ...state,
        loadingOlder: false,
        messages: mergeMessages(state.messages, action.messages),
        olderCursor: action.olderCursor,
        hasOlder: action.hasOlder,
      }
    case 'older-failed':
      return { ...state, loadingOlder: false }
    case 'merge':
      return { ...state, messages: mergeMessages(state.messages, action.messages) }
    case 'conversation-created':
      return { ...state, conversationId: action.conversationId, title: action.title }
    case 'send': {
      const exists = state.pending.some(item => item.clientMessageId === action.clientMessageId)
      return {
        ...state,
        pending: exists
          ? updatePending(state, action.clientMessageId, { status: 'sending', note: null })
          : [...state.pending, { clientMessageId: action.clientMessageId, content: action.content, messageId: null, status: 'sending', note: null }],
        streaming: { clientMessageId: action.clientMessageId, draft: '', stage: null },
      }
    }
    case 'accepted':
      return {
        ...state,
        messages: mergeMessages(state.messages, [action.message]),
        pending: updatePending(state, action.clientMessageId, { messageId: action.message.id }),
      }
    case 'stage':
      return state.streaming ? { ...state, streaming: { ...state.streaming, stage: action.stage } } : state
    case 'token':
      return state.streaming ? { ...state, streaming: { ...state.streaming, draft: state.streaming.draft + action.delta } } : state
    case 'completed':
      // The saved message replaces the streamed draft (API-CHAT-004 §4).
      return {
        ...state,
        messages: mergeMessages(state.messages, [action.message]),
        pending: state.pending.filter(item => item.clientMessageId !== action.clientMessageId),
        streaming: null,
      }
    case 'turn-failed':
      return {
        ...state,
        pending: updatePending(state, action.clientMessageId, { status: action.status, note: action.note }),
        streaming: state.streaming?.clientMessageId === action.clientMessageId ? null : state.streaming,
      }
    case 'drop-pending':
      return { ...state, pending: state.pending.filter(item => item.clientMessageId !== action.clientMessageId) }
    case 'set-title':
      return { ...state, title: action.title }
    case 'clear-highlight':
      return { ...state, highlightSeq: null }
  }
}
