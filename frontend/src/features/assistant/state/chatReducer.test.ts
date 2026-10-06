import { describe, expect, it } from 'vitest'
import type { MessageDto } from '../types'
import { chatReducer, initialChatState, mergeMessages } from './chatReducer'

function message(id: string, seq: number, role: string = 'user', content = id): MessageDto {
  return { id, seq, role, content, citations: [], refs: {}, card: null, createdAt: '2026-09-28T02:14:02Z' }
}

describe('mergeMessages', () => {
  it('sorts by seq', () => {
    expect(mergeMessages([], [message('b', 3), message('a', 1), message('c', 2)]).map(m => m.id)).toEqual(['a', 'c', 'b'])
  })

  it('de-duplicates by id, the incoming copy wins', () => {
    const merged = mergeMessages([message('a', 1, 'assistant', 'old')], [message('a', 1, 'assistant', 'new')])
    expect(merged).toHaveLength(1)
    expect(merged[0].content).toBe('new')
  })

  it('merges an older page and live messages without duplicates or gaps', () => {
    const live = [message('m3', 3), message('m4', 4, 'assistant')]
    const olderPage = [message('m2', 2, 'assistant'), message('m1', 1), message('m3', 3)]
    expect(mergeMessages(live, olderPage).map(m => m.seq)).toEqual([1, 2, 3, 4])
  })

  it('replaces the card of a message with the same id (us-061 live proposal state)', () => {
    const before = { ...message('a', 1, 'assistant'), card: { type: 'BOOKING_PROPOSAL', proposalId: 'p', status: 'PROPOSED' } }
    const after = { ...before, card: { ...before.card, status: 'CONFIRMED' } }
    expect(mergeMessages([before], [after])[0].card?.status).toBe('CONFIRMED')
  })

  it('drops roles other than user/assistant (tool messages are never shown)', () => {
    expect(mergeMessages([], [message('t', 5, 'tool')])).toEqual([])
  })
})

describe('chatReducer turn lifecycle', () => {
  it('sending → accepted → tokens → completed replaces the draft with the saved message', () => {
    let state = chatReducer(initialChatState, { type: 'send', clientMessageId: 'c1', content: 'Mốc tới?' })
    expect(state.pending[0].status).toBe('sending')
    expect(state.streaming?.clientMessageId).toBe('c1')

    state = chatReducer(state, { type: 'accepted', clientMessageId: 'c1', message: message('u1', 10) })
    expect(state.pending[0].messageId).toBe('u1')
    expect(state.messages.map(m => m.id)).toEqual(['u1'])

    state = chatReducer(state, { type: 'token', delta: 'Theo ' })
    state = chatReducer(state, { type: 'token', delta: 'sổ tay' })
    expect(state.streaming?.draft).toBe('Theo sổ tay')

    state = chatReducer(state, { type: 'completed', clientMessageId: 'c1', message: message('a1', 11, 'assistant', 'Theo sổ tay…') })
    expect(state.streaming).toBeNull()
    expect(state.pending).toEqual([])
    expect(state.messages.map(m => m.id)).toEqual(['u1', 'a1'])
  })

  it('a failed turn keeps the pending message for "Gửi lại", resend reuses the entry', () => {
    let state = chatReducer(initialChatState, { type: 'send', clientMessageId: 'c1', content: 'Hỏi' })
    state = chatReducer(state, { type: 'turn-failed', clientMessageId: 'c1', status: 'failed', note: 'Chưa gửi được.' })
    expect(state.streaming).toBeNull()
    expect(state.pending[0]).toMatchObject({ status: 'failed', note: 'Chưa gửi được.' })

    state = chatReducer(state, { type: 'send', clientMessageId: 'c1', content: 'Hỏi' })
    expect(state.pending).toHaveLength(1)
    expect(state.pending[0].status).toBe('sending')
  })
})
