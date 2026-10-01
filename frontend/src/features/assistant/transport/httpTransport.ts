import { ApiError, apiGetPaged, apiRequest, rawRequest, toApiError } from '@/shared/api/client'
import { readSseStream, StreamIdleTimeoutError } from '../sse'
import type { ConversationDto, ConversationExcerpt, MessageDto, StreamErrorPayload } from '../types'
import type { ChatTransport } from './ChatTransport'

const STREAM_IDLE_TIMEOUT_MS = 45_000

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** Thrown when the SSE stream ends without `message.completed` / `error` (EF-601). */
export class StreamInterruptedError extends ApiError {
  constructor(traceId: string | null) {
    super({ status: 0, code: 'STREAM_INTERRUPTED', message: 'The answer stream was interrupted', traceId })
  }
}

export function createHttpTransport(): ChatTransport {
  return {
    kind: 'http',

    listConversations: ({ userVehicleId, limit, cursor }) =>
      apiGetPaged<ConversationDto>(`/conversations${query({ userVehicleId, limit, cursor })}`, { timeoutMs: 10_000 }),

    createConversation: async userVehicleId =>
      (await apiRequest<ConversationDto>('/conversations', { method: 'POST', body: { userVehicleId }, timeoutMs: 10_000 })).data,

    getMessages: (conversationId, { limit, before, after }) =>
      apiGetPaged<MessageDto>(`/conversations/${encodeURIComponent(conversationId)}/messages${query({ limit, before, after })}`, {
        timeoutMs: 10_000,
      }),

    async sendMessage(conversationId, body, handlers, signal) {
      const { response, requestId } = await rawRequest(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
        method: 'POST',
        body,
        headers: { Accept: 'text/event-stream' },
        signal,
      })
      // Pre-stream checks answer with plain JSON errors (API-CHAT-004 §2).
      if (!response.ok) throw await toApiError(response, requestId)
      const traceId = response.headers.get('X-Trace-Id') ?? requestId
      if (!response.body || !(response.headers.get('Content-Type') ?? '').includes('text/event-stream')) {
        throw new StreamInterruptedError(traceId)
      }

      let finished = false
      try {
        await readSseStream(
          response.body,
          event => {
            const payload = event.data ? JSON.parse(event.data) : {}
            switch (event.event) {
              case 'message.accepted':
                handlers.onAccepted(payload.userMessage as MessageDto, Boolean(payload.replayed))
                break
              case 'status':
                handlers.onStatus(payload.stage, payload.tool)
                break
              case 'token':
                handlers.onToken(String(payload.delta ?? ''))
                break
              case 'message.completed':
                finished = true
                handlers.onCompleted(payload.message as MessageDto)
                break
              case 'error':
                finished = true
                handlers.onError(payload as StreamErrorPayload)
                break
            }
          },
          STREAM_IDLE_TIMEOUT_MS,
        )
      } catch (error) {
        if (error instanceof StreamIdleTimeoutError) throw new StreamInterruptedError(traceId)
        if (error instanceof DOMException && error.name === 'AbortError') throw error
        throw new StreamInterruptedError(traceId)
      }
      if (!finished) throw new StreamInterruptedError(traceId)
    },

    searchMessages: ({ q, userVehicleId, limit, cursor }) =>
      apiGetPaged(`/conversations/search${query({ q, userVehicleId, limit, cursor })}`, { timeoutMs: 10_000 }),

    deleteConversation: async conversationId => {
      await apiRequest<void>(`/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE', timeoutMs: 10_000 })
    },

    getConversationExcerpt: async ({ type, id }) =>
      (
        await apiRequest<ConversationExcerpt>(
          `/workshop/${type === 'booking' ? 'bookings' : 'quotes'}/${encodeURIComponent(id)}/conversation-excerpt`,
          { timeoutMs: 10_000 },
        )
      ).data,
  }
}
