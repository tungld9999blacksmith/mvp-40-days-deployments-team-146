import type { ChatAction } from '../state/chatReducer'
import type { ChatTransport } from '../transport/ChatTransport'
import type { MessageDto } from '../types'
import { QUICK_BOOKING_LABEL } from './proposalView'

export interface RunQuickBookingInput {
  transport: Pick<ChatTransport, 'createConversation' | 'quickBooking'>
  dispatch: (action: ChatAction) => void
  conversationId: string | null
  userVehicleId: string
  clientMessageId: string
  location: { lat: number; lng: number } | null
  province: string | null
  /** Called once when a new conversation had to be created first. */
  onConversationCreated?: (conversationId: string) => void
}

/**
 * us-061 UC-1501 on the client: make sure a conversation exists, show the owner's chip message,
 * then ask the backend for a proposal (API-QB-01). Never sends a chat message and never books.
 */
export async function runQuickBooking(input: RunQuickBookingInput): Promise<{ conversationId: string; assistantMessage: MessageDto }> {
  const { transport, dispatch, clientMessageId } = input
  let conversationId = input.conversationId
  if (!conversationId) {
    const conversation = await transport.createConversation(input.userVehicleId)
    conversationId = conversation.id
    dispatch({ type: 'conversation-created', conversationId: conversation.id, title: conversation.title })
    input.onConversationCreated?.(conversation.id)
  }

  dispatch({ type: 'send', clientMessageId, content: QUICK_BOOKING_LABEL })
  dispatch({ type: 'stage', stage: 'quick_booking' })
  try {
    const data = await transport.quickBooking(conversationId, {
      clientMessageId,
      location: input.location,
      province: input.province,
    })
    dispatch({ type: 'accepted', clientMessageId, message: data.userMessage })
    dispatch({ type: 'completed', clientMessageId, message: data.assistantMessage })
    return { conversationId, assistantMessage: data.assistantMessage }
  } catch (error) {
    // Drop the local chip message: a "resend" would send it as a chat question instead.
    dispatch({ type: 'turn-failed', clientMessageId, status: 'failed', note: null })
    dispatch({ type: 'drop-pending', clientMessageId })
    throw error
  }
}
