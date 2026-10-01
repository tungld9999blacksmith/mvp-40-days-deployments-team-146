import { ApiError } from '@/shared/api/client'
import { onSessionEnd } from '@/shared/session/sessionCache'
import { newId } from '@/shared/utils/id'
import type { CitationDto, ConversationDto, ConversationExcerpt, MessageDto, SearchResultDto } from '../types'
import type { ChatTransport } from './ChatTransport'

/**
 * In-memory simulation of the chat contract (same events and payloads as the real
 * API). Answers are canned demo text — they are NOT model output and NOT real data.
 */

interface MockConversation extends ConversationDto {
  messages: MessageDto[]
  clientIds: Map<string, string> // clientMessageId → user message id
}

const conversations = new Map<string, MockConversation>()
let seq = 1000

onSessionEnd(() => conversations.clear())

const MANUAL: CitationDto = {
  title: 'Sổ tay bảo dưỡng VF6',
  version: '2.1',
  documentType: 'maintenance_manual',
  pageNumber: 42,
  snippet: 'Mốc 12.000 km / 12 tháng: kiểm tra hệ thống phanh, kiểm tra pin cao áp, thay lọc gió điều hoà, đảo lốp.',
}
const WARRANTY: CitationDto = {
  title: 'Chính sách bảo hành xe điện VinFast',
  version: '2025.1',
  documentType: 'warranty_policy',
  pageNumber: 8,
  snippet: 'Pin cao áp được bảo hành theo thời hạn và giới hạn km ghi trên sổ bảo hành của từng mẫu xe.',
}

const ANSWERS: { keywords: string[]; text: string; citations: CitationDto[] }[] = [
  {
    keywords: ['mốc', 'bảo dưỡng', 'hạng mục', 'đến hạn'],
    text:
      '(Dữ liệu minh hoạ) Theo sổ tay bảo dưỡng, mốc 12.000 km / 12 tháng gồm:\n' +
      '- Kiểm tra hệ thống phanh\n- Kiểm tra pin cao áp\n- Thay lọc gió điều hoà\n- Đảo lốp\n\n' +
      '**Kiểm tra pin cao áp** thuộc diện bảo hành. Các hạng mục còn lại tính phí theo bảng giá của xưởng.',
    citations: [MANUAL, WARRANTY],
  },
  {
    keywords: ['bảo hành', 'pin', 'miễn phí'],
    text:
      '(Dữ liệu minh hoạ) Pin cao áp được bảo hành theo thời hạn và giới hạn km ghi trên sổ bảo hành của mẫu xe. ' +
      'Bạn có thể xem thời hạn cụ thể của xe mình trong mục **Xe của tôi → Bảo hành**.',
    citations: [WARRANTY],
  },
]

const REFUSAL =
  '(Dữ liệu minh hoạ) Hiện chưa có dữ liệu chính hãng cho câu hỏi này, nên tôi không thể đưa ra câu trả lời chắc chắn. ' +
  'Bạn vui lòng liên hệ xưởng dịch vụ để được tư vấn.'

function normalize(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase()
}

function answerFor(question: string) {
  const q = normalize(question)
  return ANSWERS.find(answer => answer.keywords.some(keyword => q.includes(normalize(keyword)))) ?? {
    text: REFUSAL,
    citations: [],
  }
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })

function notFound(): ApiError {
  return new ApiError({ status: 404, code: 'CONVERSATION_NOT_FOUND', message: 'Conversation was not found.' })
}

function page<T>(items: T[], limit: number, cursorIndex: number) {
  const slice = items.slice(cursorIndex, cursorIndex + limit)
  const hasMore = cursorIndex + limit < items.length
  return { data: slice, page: { nextCursor: hasMore ? String(cursorIndex + limit) : null, hasMore } }
}

function newMessage(role: 'user' | 'assistant', content: string, citations: CitationDto[] = []): MessageDto {
  seq += 1
  return { id: newId(), seq, role, content, citations, refs: {}, card: null, createdAt: new Date().toISOString() }
}

export function createMockTransport(): ChatTransport {
  return {
    kind: 'mock',

    async listConversations({ userVehicleId, limit, cursor }) {
      const items = [...conversations.values()]
        .filter(c => !userVehicleId || c.userVehicleId === userVehicleId)
        .sort((a, b) => b.lastMessageAt.localeCompare(a.lastMessageAt))
        .map(({ messages, clientIds: _clientIds, ...dto }) => ({
          ...dto,
          lastMessagePreview: messages[messages.length - 1]?.content.slice(0, 100) ?? null,
        }))
      return page(items, limit, Number(cursor ?? 0))
    },

    async createConversation(userVehicleId) {
      const now = new Date().toISOString()
      const conversation: MockConversation = {
        id: newId(),
        userVehicleId,
        title: null,
        lastMessageAt: now,
        createdAt: now,
        messages: [],
        clientIds: new Map(),
      }
      conversations.set(conversation.id, conversation)
      const { messages: _m, clientIds: _c, ...dto } = conversation
      return dto
    },

    async getMessages(conversationId, { limit, before, after }) {
      const conversation = conversations.get(conversationId)
      if (!conversation) throw notFound()
      const all = conversation.messages
      if (after !== undefined) {
        const newer = all.filter(m => m.seq > after)
        const data = newer.slice(0, limit)
        const last = data[data.length - 1]
        return { data, page: { nextCursor: last ? String(last.seq) : null, hasMore: newer.length > limit } }
      }
      const older = all.filter(m => before === undefined || m.seq < before).reverse()
      const data = older.slice(0, limit)
      const last = data[data.length - 1]
      return { data, page: { nextCursor: last ? String(last.seq) : null, hasMore: older.length > limit } }
    },

    async sendMessage(conversationId, body, handlers, signal) {
      const conversation = conversations.get(conversationId)
      if (!conversation) throw notFound()

      // Idempotency on clientMessageId (BR-611).
      const existingId = conversation.clientIds.get(body.clientMessageId)
      if (existingId) {
        const userMessage = conversation.messages.find(m => m.id === existingId)!
        const answer = conversation.messages.find(m => m.role === 'assistant' && m.seq > userMessage.seq)
        if (answer) {
          handlers.onAccepted(userMessage, true)
          handlers.onCompleted(answer)
          return
        }
      }

      await wait(150, signal)
      let userMessage = existingId ? conversation.messages.find(m => m.id === existingId) : undefined
      if (!userMessage) {
        userMessage = newMessage('user', body.content)
        conversation.messages.push(userMessage)
        conversation.clientIds.set(body.clientMessageId, userMessage.id)
        conversation.title ??= body.content.slice(0, 80)
        conversation.lastMessageAt = userMessage.createdAt
      }
      handlers.onAccepted(userMessage, false)

      handlers.onStatus('retrieving')
      await wait(600, signal)
      handlers.onStatus('generating')
      const answer = answerFor(body.content)
      for (let index = 0; index < answer.text.length; index += 6) {
        await wait(25, signal)
        handlers.onToken(answer.text.slice(index, index + 6))
      }
      const assistant = newMessage('assistant', answer.text, answer.citations)
      conversation.messages.push(assistant)
      conversation.lastMessageAt = assistant.createdAt
      handlers.onCompleted(assistant)
    },

    async searchMessages({ q, userVehicleId, limit, cursor }) {
      const needle = normalize(q.trim())
      const results: SearchResultDto[] = []
      for (const conversation of conversations.values()) {
        if (userVehicleId && conversation.userVehicleId !== userVehicleId) continue
        for (const message of conversation.messages) {
          const index = normalize(message.content).indexOf(needle)
          if (index === -1) continue
          const start = Math.max(0, index - 60)
          const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          const snippet =
            (start > 0 ? '… ' : '') +
            escape(message.content.slice(start, index)) +
            '<mark>' +
            escape(message.content.slice(index, index + q.trim().length)) +
            '</mark>' +
            escape(message.content.slice(index + q.trim().length, index + 140))
          results.push({
            conversationId: conversation.id,
            conversationTitle: conversation.title,
            messageId: message.id,
            seq: message.seq,
            role: message.role,
            snippet,
            createdAt: message.createdAt,
          })
        }
      }
      results.sort((a, b) => b.seq - a.seq)
      return page(results, limit, Number(cursor ?? 0))
    },

    async deleteConversation(conversationId) {
      if (!conversations.delete(conversationId)) throw notFound()
    },

    async getConversationExcerpt({ type, id }): Promise<ConversationExcerpt> {
      const confirmedMessageId = newId()
      const at = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()
      return {
        source: { type, id, confirmedMessageId },
        messages: [
          { id: newId(), seq: 1, role: 'user', content: '(Dữ liệu minh hoạ) Xe tôi sắp đến mốc 12.000 km, chi phí khoảng bao nhiêu?', createdAt: at(12) },
          { id: newId(), seq: 2, role: 'assistant', content: '(Dữ liệu minh hoạ) Chi phí ước tính cho mốc này đã được gửi để xưởng xác nhận.', createdAt: at(11) },
          { id: confirmedMessageId, seq: 3, role: 'user', content: 'Xác nhận', createdAt: at(10) },
        ],
      }
    },
  }
}
