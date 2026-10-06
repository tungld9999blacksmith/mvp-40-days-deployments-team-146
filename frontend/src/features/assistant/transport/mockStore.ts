import { ApiError } from '@/shared/api/client'
import { DEMO_MODE } from '@/shared/config/env'
import { onSessionEnd } from '@/shared/session/sessionCache'
import { newId } from '@/shared/utils/id'
import type { CitationDto, ConversationDto, MessageDto } from '../types'

/**
 * Conversations of the mock chat transport. In memory and cleared when the session ends; demo mode
 * stands in for the server instead: the chat is kept in localStorage, survives reloads, logout and
 * portal switches, and the Workshop Portal in another tab sees it (conversation excerpt).
 */
export interface MockConversation extends ConversationDto {
  messages: MessageDto[]
  clientIds: Map<string, string> // clientMessageId → user message id
}

export const MOCK_CHAT_STORAGE_KEY = 'evcare.mockChat.v1'

export const conversations = new Map<string, MockConversation>()
let seq = 1000

/** Other mock chat state saved with the conversations (quick-booking proposals). */
interface Section {
  save: () => unknown
  load: (data: unknown) => void
}

interface Stored {
  seq: number
  conversations: (Omit<MockConversation, 'clientIds'> & { clientIds: [string, string][] })[]
  sections: Record<string, unknown>
}

const sections = new Map<string, Section>()
let stored: Stored | null = null

function readStored(): Stored | null {
  try {
    const raw = localStorage.getItem(MOCK_CHAT_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Stored) : null
  } catch {
    return null
  }
}

function hydrate() {
  stored = readStored()
  conversations.clear()
  if (stored) {
    seq = Math.max(seq, stored.seq)
    for (const conversation of stored.conversations) conversations.set(conversation.id, { ...conversation, clientIds: new Map(conversation.clientIds) })
  }
  for (const [name, section] of sections) section.load(stored?.sections[name] ?? null)
}

/** Demo mode: writes the mock chat to localStorage (no-op otherwise). */
export function saveMockChat() {
  if (!DEMO_MODE) return
  const data: Stored = {
    seq,
    conversations: [...conversations.values()].map(conversation => ({ ...conversation, clientIds: [...conversation.clientIds] })),
    sections: Object.fromEntries([...sections].map(([name, section]) => [name, section.save()])),
  }
  try {
    localStorage.setItem(MOCK_CHAT_STORAGE_KEY, JSON.stringify(data))
  } catch {
    // storage blocked or full: the chat lasts for this page only
  }
}

export function registerMockChatSection(name: string, section: Section) {
  sections.set(name, section)
  section.load(stored?.sections[name] ?? null)
}

if (DEMO_MODE) {
  hydrate()
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', event => {
      if (event.key === MOCK_CHAT_STORAGE_KEY) hydrate()
    })
  }
}

onSessionEnd(() => {
  if (!DEMO_MODE) conversations.clear()
})

export function newMessage(
  role: 'user' | 'assistant',
  content: string,
  extra: { citations?: CitationDto[]; card?: MessageDto['card']; refs?: MessageDto['refs'] } = {},
): MessageDto {
  seq += 1
  return {
    id: newId(),
    seq,
    role,
    content,
    citations: extra.citations ?? [],
    refs: extra.refs ?? {},
    card: extra.card ?? null,
    createdAt: new Date().toISOString(),
  }
}

export function appendMessage(conversation: MockConversation, message: MessageDto): MessageDto {
  conversation.messages.push(message)
  conversation.lastMessageAt = message.createdAt
  saveMockChat()
  return message
}

export function conversationNotFound(): ApiError {
  return new ApiError({ status: 404, code: 'CONVERSATION_NOT_FOUND', message: 'Conversation was not found.' })
}

export function getConversation(conversationId: string): MockConversation {
  const conversation = conversations.get(conversationId)
  if (!conversation) throw conversationNotFound()
  return conversation
}
