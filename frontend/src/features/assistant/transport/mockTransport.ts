import { ApiError } from '@/shared/api/client'
import { newId } from '@/shared/utils/id'
import { getCostEstimate } from '@/features/estimate/api'
import type { CitationDto, ConversationExcerpt, MessageDto, SearchResultDto } from '../types'
import type { ChatTransport } from './ChatTransport'
import {
  cancelProposal,
  confirmProposal,
  enrichMessage,
  excerptForBooking,
  proposeFromChat,
  quickBooking,
  reviseProposal,
} from './mockQuickBooking'
import { appendMessage, conversations, getConversation, newMessage, saveMockChat, type MockConversation } from './mockStore'

/**
 * In-memory simulation of the chat contract (same events and payloads as the real
 * API). Answers are canned demo text — they are NOT model output and NOT real data.
 * Quick booking (us-061) runs on the same slot and booking APIs as the app (mockQuickBooking).
 */

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
const OWNER_MANUAL: CitationDto = {
  title: 'Hướng dẫn sử dụng xe VF6',
  version: '1.3',
  documentType: 'owner_manual',
  pageNumber: 118,
  snippet: 'Nên duy trì mức sạc trong khoảng 20% đến 80% cho nhu cầu di chuyển hằng ngày để tối ưu tuổi thọ pin.',
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
    keywords: ['bảo hành', 'miễn phí'],
    text:
      '(Dữ liệu minh hoạ) Pin cao áp được bảo hành theo thời hạn và giới hạn km ghi trên sổ bảo hành của mẫu xe. ' +
      'Bạn có thể xem thời hạn cụ thể của xe mình trong mục **Xe của tôi → Bảo hành**.',
    citations: [WARRANTY],
  },
  {
    keywords: ['sạc', 'pin', 'quãng đường'],
    text:
      '(Dữ liệu minh hoạ) Để pin cao áp bền hơn, nên giữ mức sạc hằng ngày trong khoảng **20–80%** và chỉ sạc đầy trước chuyến đi dài. ' +
      'Hạn chế sạc nhanh DC liên tục khi pin còn nóng. Nếu quãng đường đi được giảm bất thường, bạn nên đặt lịch kiểm tra pin tại xưởng.',
    citations: [OWNER_MANUAL, WARRANTY],
  },
  {
    keywords: ['phanh', 'lốp', 'tiếng kêu', 'rung'],
    text:
      '(Dữ liệu minh hoạ) Hệ thống phanh và lốp được kiểm tra ở mỗi mốc 12.000 km. Nếu nghe tiếng kêu khi phanh, xe rung ở tốc độ thấp ' +
      'hoặc lốp mòn không đều, bạn nên đưa xe tới xưởng sớm thay vì chờ tới mốc bảo dưỡng.',
    citations: [MANUAL],
  },
]

const REFUSAL =
  '(Dữ liệu minh hoạ) Hiện chưa có dữ liệu chính hãng cho câu hỏi này, nên tôi không thể đưa ra câu trả lời chắc chắn. ' +
  'Bạn vui lòng liên hệ xưởng dịch vụ để được tư vấn.'

function normalize(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase()
}

/** A booking request typed in the chat gets a proposal card (TOOL-QB-01 `propose_booking`). */
function wantsBooking(question: string): boolean {
  return /\b(dat|book)\s*(lich|hen)|\bhen lich\b|\bdat lich\b/.test(normalize(question))
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

function page<T>(items: T[], limit: number, cursorIndex: number) {
  const slice = items.slice(cursorIndex, cursorIndex + limit)
  const hasMore = cursorIndex + limit < items.length
  return { data: slice, page: { nextCursor: hasMore ? String(cursorIndex + limit) : null, hasMore } }
}

/**
 * Demo of the F5 cards (CARD-EST, us-045 §4.7): a cost question gets the estimate from the same
 * API-EST-02 the `/estimate` screen uses, so the card and the detail show the same total.
 */
async function cardFor(content: string, userVehicleId: string): Promise<MessageDto['card']> {
  if (!/chi ph[ií]|gi[aá] bao nhi[eê]u|d[uự] to[aá]n/i.test(content)) return null
  try {
    const estimate = await getCostEstimate(userVehicleId, { odoMilestone: null, workshopId: null }).catch(async (error: unknown) => {
      const valid = (error as { details?: { validMilestones?: number[] } }).details?.validMilestones
      if (!valid?.length) throw error
      return getCostEstimate(userVehicleId, { odoMilestone: valid[0], workshopId: null })
    })
    return estimate.status === 'READY' ? { type: 'ESTIMATE', estimate } : null
  } catch {
    return null
  }
}

/** Answer of a chat turn: canned text + citations, an estimate card, or a booking proposal. */
async function replyTo(conversation: MockConversation, content: string) {
  if (wantsBooking(content)) {
    try {
      const proposal = await proposeFromChat(conversation)
      return { text: proposal.text, citations: [] as CitationDto[], card: proposal.card, refs: proposal.refs, link: proposal.link }
    } catch {
      // fall back to a canned answer (e.g. the vehicle data is not reachable)
    }
  }
  const answer = answerFor(content)
  return { text: answer.text, citations: answer.citations, card: await cardFor(content, conversation.userVehicleId), refs: {}, link: () => {} }
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
      saveMockChat()
      const { messages: _m, clientIds: _c, ...dto } = conversation
      return dto
    },

    async getMessages(conversationId, { limit, before, after }) {
      const all = getConversation(conversationId).messages
      if (after !== undefined) {
        const newer = all.filter(m => m.seq > after)
        const data = await Promise.all(newer.slice(0, limit).map(enrichMessage))
        const last = data[data.length - 1]
        return { data, page: { nextCursor: last ? String(last.seq) : null, hasMore: newer.length > limit } }
      }
      const older = all.filter(m => before === undefined || m.seq < before).reverse()
      const data = await Promise.all(older.slice(0, limit).map(enrichMessage))
      const last = data[data.length - 1]
      return { data, page: { nextCursor: last ? String(last.seq) : null, hasMore: older.length > limit } }
    },

    async sendMessage(conversationId, body, handlers, signal) {
      const conversation = getConversation(conversationId)

      // Idempotency on clientMessageId (BR-611).
      const existingId = conversation.clientIds.get(body.clientMessageId)
      if (existingId) {
        const userMessage = conversation.messages.find(m => m.id === existingId)!
        const answer = conversation.messages.find(m => m.role === 'assistant' && m.seq > userMessage.seq)
        if (answer) {
          handlers.onAccepted(userMessage, true)
          handlers.onCompleted(await enrichMessage(answer))
          return
        }
      }

      await wait(150, signal)
      let userMessage = existingId ? conversation.messages.find(m => m.id === existingId) : undefined
      if (!userMessage) {
        userMessage = appendMessage(conversation, newMessage('user', body.content))
        conversation.clientIds.set(body.clientMessageId, userMessage.id)
        conversation.title ??= body.content.slice(0, 80)
      }
      handlers.onAccepted(userMessage, false)

      handlers.onStatus('retrieving')
      await wait(600, signal)
      const booking = wantsBooking(body.content)
      if (booking) handlers.onStatus('calling_tool', 'propose_booking')
      const reply = await replyTo(conversation, body.content)
      handlers.onStatus('generating')
      for (let index = 0; index < reply.text.length; index += 6) {
        await wait(25, signal)
        handlers.onToken(reply.text.slice(index, index + 6))
      }
      const assistant = appendMessage(conversation, newMessage('assistant', reply.text, { citations: reply.citations, card: reply.card, refs: reply.refs }))
      reply.link(assistant)
      handlers.onCompleted(await enrichMessage(assistant))
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
      getConversation(conversationId)
      conversations.delete(conversationId)
      saveMockChat()
    },

    /** Only bookings made from a chat proposal have a conversation; others hide the panel. */
    async getConversationExcerpt({ id }): Promise<ConversationExcerpt> {
      const excerpt = excerptForBooking(id)
      if (!excerpt) throw new ApiError({ status: 404, code: 'BOOKING_NOT_FOUND', message: 'No conversation for this booking.' })
      return excerpt
    },

    quickBooking,
    confirmProposal,
    reviseProposal,
    cancelProposal,
  }
}
