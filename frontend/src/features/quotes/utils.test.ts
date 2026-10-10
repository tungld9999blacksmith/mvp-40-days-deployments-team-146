import { describe, expect, it } from 'vitest'
import { hasConversation, hasUnseenResult, isWaitingLong, waitingHours } from './utils'

const NOW = new Date('2026-10-02T12:00:00Z')

describe('quote utils', () => {
  it('flags only reviewed quotes the owner has not opened (BR-1109)', () => {
    expect(hasUnseenResult({ status: 'APPROVED', resultSeen: false })).toBe(true)
    expect(hasUnseenResult({ status: 'REJECTED', resultSeen: false })).toBe(true)
    expect(hasUnseenResult({ status: 'APPROVED', resultSeen: true })).toBe(false)
    // API-QT-02 sends resultSeen=false for quotes without a result yet.
    expect(hasUnseenResult({ status: 'PENDING_APPROVAL', resultSeen: false })).toBe(false)
    expect(hasUnseenResult({ status: 'DRAFT', resultSeen: false })).toBe(false)
  })

  it('counts whole waiting hours from submission', () => {
    expect(waitingHours({ submittedAt: '2026-10-01T11:30:00Z' }, NOW)).toBe(24)
    expect(waitingHours({ submittedAt: null }, NOW)).toBe(0)
  })

  it('marks a pending quote waiting 24h or more (Q-1105)', () => {
    expect(isWaitingLong({ status: 'PENDING_APPROVAL', submittedAt: '2026-10-01T12:00:00Z' }, NOW)).toBe(true)
    expect(isWaitingLong({ status: 'PENDING_APPROVAL', submittedAt: '2026-10-01T12:30:00Z' }, NOW)).toBe(false)
    expect(isWaitingLong({ status: 'APPROVED', submittedAt: '2026-09-20T12:00:00Z' }, NOW)).toBe(false)
  })

  it('shows the conversation panel only when the excerpt link exists', () => {
    expect(hasConversation({ conversationExcerptUrl: '/api/v1/workshop/quotes/q1/conversation-excerpt' })).toBe(true)
    expect(hasConversation({ conversationExcerptUrl: null })).toBe(false)
  })
})
