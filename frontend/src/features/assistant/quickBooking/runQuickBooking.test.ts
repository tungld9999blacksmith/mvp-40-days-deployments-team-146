import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/shared/api/client'
import type { ChatAction } from '../state/chatReducer'
import type { ConversationDto, MessageDto } from '../types'
import { runQuickBooking } from './runQuickBooking'

const message = (id: string, role: string, card: MessageDto['card'] = null): MessageDto => ({
  id,
  seq: 1,
  role,
  content: id,
  citations: [],
  refs: {},
  card,
  createdAt: '2026-10-03T03:00:00Z',
})

function fakeTransport() {
  const conversation: ConversationDto = {
    id: 'c-new',
    userVehicleId: 'v-1',
    title: null,
    lastMessageAt: '2026-10-03T03:00:00Z',
    createdAt: '2026-10-03T03:00:00Z',
  }
  return {
    createConversation: vi.fn(async () => conversation),
    quickBooking: vi.fn(async () => ({
      userMessage: message('u-1', 'user'),
      assistantMessage: message('a-1', 'assistant', { type: 'BOOKING_PROPOSAL', proposalId: 'p-1' }),
      replayed: false,
    })),
    sendMessage: vi.fn(),
  }
}

describe('runQuickBooking', () => {
  it('creates the conversation first, then asks for a proposal — never a chat message', async () => {
    const transport = fakeTransport()
    const actions: ChatAction[] = []
    const created: string[] = []

    const result = await runQuickBooking({
      transport,
      dispatch: action => actions.push(action),
      conversationId: null,
      userVehicleId: 'v-1',
      clientMessageId: 'cm-1',
      location: { lat: 21, lng: 105.8 },
      province: null,
      onConversationCreated: id => created.push(id),
    })

    expect(transport.createConversation).toHaveBeenCalledWith('v-1')
    expect(transport.quickBooking).toHaveBeenCalledWith('c-new', {
      clientMessageId: 'cm-1',
      location: { lat: 21, lng: 105.8 },
      province: null,
    })
    expect(transport.sendMessage).not.toHaveBeenCalled()
    expect(created).toEqual(['c-new'])
    expect(actions.map(a => a.type)).toEqual(['conversation-created', 'send', 'stage', 'accepted', 'completed'])
    expect(result.assistantMessage.card?.type).toBe('BOOKING_PROPOSAL')
  })

  it('reuses an existing conversation', async () => {
    const transport = fakeTransport()
    await runQuickBooking({
      transport,
      dispatch: () => {},
      conversationId: 'c-1',
      userVehicleId: 'v-1',
      clientMessageId: 'cm-1',
      location: null,
      province: 'Hà Nội',
    })
    expect(transport.createConversation).not.toHaveBeenCalled()
    expect(transport.quickBooking).toHaveBeenCalledWith('c-1', { clientMessageId: 'cm-1', location: null, province: 'Hà Nội' })
  })

  it('drops the local chip message on failure so it cannot be resent as a chat question', async () => {
    const transport = fakeTransport()
    transport.quickBooking.mockRejectedValueOnce(new ApiError({ status: 409, code: 'CONVERSATION_BUSY', message: 'busy' }))
    const actions: ChatAction[] = []

    await expect(
      runQuickBooking({
        transport,
        dispatch: action => actions.push(action),
        conversationId: 'c-1',
        userVehicleId: 'v-1',
        clientMessageId: 'cm-1',
        location: null,
        province: null,
      }),
    ).rejects.toMatchObject({ code: 'CONVERSATION_BUSY' })
    expect(actions.map(a => a.type)).toEqual(['send', 'stage', 'turn-failed', 'drop-pending'])
  })
})
