import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getDb, resetDb } from '@/mocks/server/db'
import { skipOwnerOnboarding } from '@/mocks/server/demo'
import { isApiError } from '@/shared/api/client'
import { listMyBookings } from '@/features/bookings/api'
import type { BookingProposalCard, MessageDto } from '../types'
import { createMockTransport } from './mockTransport'
import { proposeFromChat } from './mockQuickBooking'
import { conversations } from './mockStore'

// Demo mode: every API call of the transport is answered by the in-browser mock API.
vi.mock('@/shared/config/env', async importOriginal => ({
  ...(await importOriginal<typeof import('@/shared/config/env')>()),
  DEMO_MODE: true,
  API_MOCKS: 'demo',
}))

const VEHICLE = 'demo-owner-vehicle'
const transport = createMockTransport()

function cardOf(message: MessageDto): BookingProposalCard {
  expect(message.card?.type).toBe('BOOKING_PROPOSAL')
  return message.card as unknown as BookingProposalCard
}

async function propose(location: { lat: number; lng: number } | null = null) {
  const conversation = await transport.createConversation(VEHICLE)
  const result = await transport.quickBooking(conversation.id, { clientMessageId: crypto.randomUUID(), location, province: null })
  return { conversationId: conversation.id, ...result }
}

async function errorOf(promise: Promise<unknown>) {
  try {
    await promise
  } catch (error) {
    if (isApiError(error)) return error
    throw error
  }
  throw new Error('expected an ApiError')
}

beforeEach(() => {
  // Monday 09:00 in Vietnam.
  vi.useFakeTimers({ now: new Date('2026-10-05T02:00:00Z'), toFake: ['Date'] })
  resetDb()
  conversations.clear()
  // Returning owner: 600 km / 12 days to the 24,000 km milestone, profile in Hà Nội.
  skipOwnerOnboarding()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('mock quick booking (us-061)', () => {
  it('proposes the earliest slot near the profile area, without booking anything', async () => {
    const { assistantMessage, userMessage } = await propose()
    expect(userMessage.content).toBe('Đặt lịch bảo dưỡng nhanh')
    expect(assistantMessage.refs.inReplyTo).toBe(userMessage.id)
    const card = cardOf(assistantMessage)
    expect(card.status).toBe('PROPOSED')
    expect(card.locationBasis).toBe('PROVINCE')
    expect(card.locationLabel).toBe('Xưởng trong khu vực Hà Nội')
    expect(card.milestone?.odoMilestoneKm).toBe(24_000)
    expect(card.primary.region).toBe('Hà Nội')
    expect(card.primary.distanceKm).toBeNull()
    expect(card.primary.estimate?.chargeableTotal).toMatch(/^\d+$/)
    expect(card.alternatives.length).toBeLessThanOrEqual(2)
    // BR-1504: at least 2 hours ahead.
    expect(new Date(`${card.primary.date}T${card.primary.timeSlot}:00+07:00`).getTime()).toBeGreaterThanOrEqual(Date.now() + 2 * 3_600_000)
    expect(assistantMessage.content).toMatch(/^Xe còn 600 km \/ 12 ngày tới mốc 24\.000 km/)
    expect((await listMyBookings('UPCOMING')).items).toHaveLength(0)
  })

  it('ranks by distance from the device position', async () => {
    const card = cardOf((await propose({ lat: 20.994, lng: 105.808 })).assistantMessage)
    expect(card.locationBasis).toBe('DEVICE')
    expect(card.primary.workshopName).toBe('VinFast Thanh Xuân')
    expect(card.primary.distanceKm).toBeLessThan(1)
  })

  it('books once on confirm, replays the same booking, and shows the live status on reload', async () => {
    const { conversationId, assistantMessage } = await propose()
    const card = cardOf(assistantMessage)
    const first = await transport.confirmProposal(conversationId, card.proposalId)
    expect(first.replayed).toBe(false)
    expect(first.booking.status).toBe('PENDING')
    expect(first.booking.bookingCode).toBeNull()
    expect(first.message?.content).toMatch(/Xưởng sẽ xác nhận trong tối đa 12 giờ/)

    const again = await transport.confirmProposal(conversationId, card.proposalId)
    expect(again.replayed).toBe(true)
    expect(again.booking.bookingId).toBe(first.booking.bookingId)
    expect((await listMyBookings('UPCOMING')).items).toHaveLength(1)

    const page = await transport.getMessages(conversationId, { limit: 50 })
    const reloaded = cardOf(page.data.find(message => message.id === assistantMessage.id)!)
    expect(reloaded.status).toBe('CONFIRMED')
    expect(reloaded.booking?.bookingId).toBe(first.booking.bookingId)

    // BR-013: the next quick booking points at the open booking instead of proposing.
    const next = await transport.quickBooking(conversationId, { clientMessageId: crypto.randomUUID(), location: null, province: null })
    expect(next.assistantMessage.card).toBeNull()
    expect(next.assistantMessage.refs.bookingId).toBe(first.booking.bookingId)

    // The Workshop Portal sees the conversation that led to the booking.
    const excerpt = await transport.getConversationExcerpt({ type: 'booking', id: first.booking.bookingId })
    expect(excerpt.source.confirmedMessageId).toBe(assistantMessage.id)
    expect(excerpt.messages.at(-1)?.id).toBe(assistantMessage.id)
    expect((await errorOf(transport.getConversationExcerpt({ type: 'booking', id: 'other' }))).code).toBe('BOOKING_NOT_FOUND')
  })

  it('revises to another offered slot and retires the old proposal', async () => {
    const { conversationId, assistantMessage } = await propose()
    const card = cardOf(assistantMessage)
    const target = card.alternatives[0] ?? card.primary
    const revised = await transport.reviseProposal(conversationId, card.proposalId, {
      workshopId: target.workshopId,
      date: target.date,
      timeSlot: '15:00',
    })
    const next = cardOf(revised.message)
    expect(next.primary).toMatchObject({ workshopId: target.workshopId, timeSlot: '15:00' })
    expect((await errorOf(transport.confirmProposal(conversationId, card.proposalId))).code).toBe('PROPOSAL_INACTIVE')
    expect((await errorOf(transport.reviseProposal(conversationId, revised.proposalId, { workshopId: 'elsewhere', date: target.date, timeSlot: '15:00' }))).code).toBe(
      'REVISE_WORKSHOP_NOT_OFFERED',
    )
  })

  it('cancels a proposal for good', async () => {
    const { conversationId, assistantMessage } = await propose()
    const { proposalId } = cardOf(assistantMessage)
    expect((await transport.cancelProposal(conversationId, proposalId)).status).toBe('CANCELLED')
    expect((await transport.cancelProposal(conversationId, proposalId)).status).toBe('CANCELLED')
    expect((await errorOf(transport.confirmProposal(conversationId, proposalId))).code).toBe('PROPOSAL_INACTIVE')
  })

  it('offers a new proposal instead of booking when the slot filled up meanwhile', async () => {
    const { conversationId, assistantMessage } = await propose()
    const card = cardOf(assistantMessage)
    const db = getDb()
    const filler = db.bookings.find(booking => !booking.ownerSelf)!
    for (let index = 0; index < 3; index += 1) {
      db.bookings.push({ ...filler, bookingId: `filler-${index}`, status: 'confirmed', bookingDate: card.primary.date, timeSlot: card.primary.timeSlot })
    }
    const error = await errorOf(transport.confirmProposal(conversationId, card.proposalId))
    expect(error.code).toBe('PROPOSAL_SLOT_FULL')
    const replacement = cardOf(error.details!.message as MessageDto)
    expect(error.details!.proposalId).toBe(replacement.proposalId)
    expect(`${replacement.primary.date} ${replacement.primary.timeSlot}`).not.toBe(`${card.primary.date} ${card.primary.timeSlot}`)
    expect((await listMyBookings('UPCOMING')).items).toHaveLength(0)
  })

  it('answers a booking request typed in the chat with a proposal card', async () => {
    const conversation = await transport.createConversation(VEHICLE)
    const reply = await proposeFromChat(conversations.get(conversation.id)!)
    expect(reply.card?.type).toBe('BOOKING_PROPOSAL')
    expect(reply.text).toMatch(/Bấm "Xác nhận đặt lịch"/)
  })
})
