import { beforeEach, describe, expect, it } from 'vitest'
import { classify } from './crm'
import { getDb, resetDb, todayVn } from './db'
import { configure, handleRequest } from './index'

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

async function call(method: Method, path: string, body?: unknown, headers: Record<string, string> = {}) {
  const response = await handleRequest({ method, path, body, headers: new Headers(headers) })
  if (!response) return { status: 0, data: null as never, error: null as never }
  const text = await response.text()
  const json = text ? JSON.parse(text) : null
  return { status: response.status, data: json?.data, error: json?.error }
}

const VEHICLE = 'veh-1'
const WORKSHOP = 'ws-1'

beforeEach(() => {
  resetDb()
  configure('all')
  const db = getDb()
  db.owner = { fullName: 'Chủ xe Test', phone: '0901234567' }
  db.vehicles.push({
    userVehicleId: VEHICLE,
    modelId: 'VF5',
    modelName: 'VinFast VF 5 Plus',
    licensePlate: '30A12345',
    nextOdoMilestone: 24_000,
    nextItems: [],
    warrantyStatus: 'ACTIVE',
  })
  db.workshops.push({ workshopId: WORKSHOP, name: 'Xưởng Test', address: 'Hà Nội', phone: '024 1111 2222', region: 'Hà Nội', active: true, isPreferred: true })
})

describe('us-045 estimate', () => {
  it('totals only the chargeable lines (BR-1001) and uses the preferred workshop', async () => {
    const result = await call('GET', `/user-vehicles/${VEHICLE}/cost-estimate`)
    expect(result.status).toBe(200)
    const estimate = result.data
    expect(estimate.status).toBe('READY')
    expect(estimate.workshop.selectedBy).toBe('PREFERRED')
    expect(estimate.milestone.odoMilestone).toBe(24_000)
    const sum = estimate.items.filter((item: { covered: boolean }) => !item.covered).reduce((total: number, item: { price: number }) => total + item.price, 0)
    expect(estimate.chargeableTotal).toBe(sum)
    expect(estimate.items.some((item: { covered: boolean; price: number }) => item.covered && item.price === 0)).toBe(true)
  })

  it('charges every line once the warranty expired (AF-1004)', async () => {
    getDb().vehicles[0].warrantyStatus = 'EXPIRED'
    const { data } = await call('GET', `/user-vehicles/${VEHICLE}/cost-estimate?odoMilestone=12000&workshopId=${WORKSHOP}`)
    expect(data.coveredCount).toBe(0)
    expect(data.workshop.selectedBy).toBe('REQUEST')
  })

  it('rejects a milestone outside the rules with the valid list (BR-1002)', async () => {
    const { status, error } = await call('GET', `/user-vehicles/${VEHICLE}/cost-estimate?odoMilestone=13000`)
    expect(status).toBe(422)
    expect(error.code).toBe('MILESTONE_NOT_FOUND')
    expect(error.details.validMilestones).toContain(12_000)
  })

  it('returns NO_RULE without any number for a model without rules (BR-1009)', async () => {
    getDb().vehicles[0].modelId = 'VF3'
    const { data } = await call('GET', `/user-vehicles/${VEHICLE}/cost-estimate`)
    expect(data).toMatchObject({ status: 'NO_RULE', chargeableTotal: null, items: [] })
  })
})

describe('us-037 / us-057 board and progress', () => {
  it('walks a booking from check-in to completion with progress and a follow-up', async () => {
    const board = await call('GET', `/workshop-owner/bookings?from=${todayVn()}&to=${todayVn()}`)
    const confirmed = board.data.items.find((item: { status: string; allowedActions: string[] }) => item.status === 'CONFIRMED' && item.allowedActions.includes('CHECK_IN'))
    expect(confirmed).toBeTruthy()
    const id = confirmed.bookingId
    const path = `/workshop-owner/bookings/${id}/transitions`

    const stale = await call('POST', path, { action: 'START', expectedStatus: 'CHECKED_IN' })
    expect(stale.error.code).toBe('INVALID_STATUS_TRANSITION')
    expect(stale.error.details.currentStatus).toBe('CONFIRMED')

    expect((await call('POST', path, { action: 'CHECK_IN', expectedStatus: 'CONFIRMED', source: 'QR_SCAN' })).data.status).toBe('CHECKED_IN')
    // Scanning the same QR again is idempotent (EDGE-805).
    expect((await call('POST', path, { action: 'CHECK_IN', expectedStatus: 'CONFIRMED' })).status).toBe(200)
    expect((await call('POST', path, { action: 'START', expectedStatus: 'CHECKED_IN' })).data.status).toBe('IN_PROGRESS')

    const progressPath = `/workshop-owner/bookings/${id}/progress`
    let progress = (await call('GET', progressPath)).data
    expect(progress.currentStage).toBe('INSPECTING')
    expect(progress.nextStages).toEqual(['SERVICING'])
    progress = (await call('POST', progressPath, { stage: 'SERVICING', expectedCurrentStage: 'INSPECTING' })).data
    const shortNote = await call('POST', progressPath, { stage: 'WAITING_PARTS', note: 'chờ', expectedCurrentStage: 'SERVICING' })
    expect(shortNote.error.code).toBe('NOTE_REQUIRED')
    const wrongOrder = await call('POST', progressPath, { stage: 'READY_FOR_PICKUP', expectedCurrentStage: 'SERVICING' })
    expect(wrongOrder.error.details.nextStages).toEqual(['WAITING_PARTS', 'QUALITY_CHECK'])
    await call('POST', progressPath, { stage: 'QUALITY_CHECK', expectedCurrentStage: 'SERVICING' })
    const raced = await call('POST', progressPath, { stage: 'READY_FOR_PICKUP', expectedCurrentStage: 'SERVICING' })
    expect(raced.error.code).toBe('PROGRESS_CHANGED')
    await call('POST', progressPath, { stage: 'READY_FOR_PICKUP', expectedCurrentStage: 'QUALITY_CHECK' })

    const done = await call('POST', path, { action: 'COMPLETE', expectedStatus: 'IN_PROGRESS', actualCost: 1_850_000 })
    expect(done.data.status).toBe('COMPLETED')
    expect(done.data.effects.followUpId).toBeTruthy()
    const frozen = (await call('GET', progressPath)).data
    expect(frozen).toMatchObject({ isFrozen: true, nextStages: [] })
  })

  it('caps slot blocks at the free capacity (BR-809)', async () => {
    const capacity = (await call('GET', '/workshop-owner/capacity')).data
    const day = capacity.days.find((item: { isClosed: boolean }) => !item.isClosed)
    const slot = day.slots[day.slots.length - 1]
    const tooMany = await call('PUT', '/workshop-owner/slot-blocks', { date: day.date, timeSlot: slot.timeSlot, blockedCount: slot.maxBlock + 1, reason: 'WALK_IN' })
    expect(tooMany.error.code).toBe('BLOCK_EXCEEDS_FREE_CAPACITY')
    const ok = await call('PUT', '/workshop-owner/slot-blocks', { date: day.date, timeSlot: slot.timeSlot, blockedCount: slot.maxBlock, reason: 'WALK_IN' })
    expect(ok.data.remaining).toBe(0)
  })
})

describe('us-033 / us-053 owner ticket', () => {
  it('reschedules within the same workshop, keeps the code, then cancels idempotently', async () => {
    const upcoming = (await call('GET', '/bookings?scope=UPCOMING')).data.items
    const target = upcoming.find((item: { allowedActions: string[] }) => item.allowedActions.includes('RESCHEDULE'))
    expect(target).toBeTruthy()
    const ticket = (await call('GET', `/bookings/${target.bookingId}`)).data
    expect(ticket.qrPayload).toContain(`/c/${ticket.bookingCode}`)
    expect(ticket.vehicle.plateMasked).toContain('***')

    let token: string | null = null
    let chosen: { date: string; slot: string } | null = null
    for (let offset = 1; offset < 7 && !token; offset += 1) {
      const date = new Date(Date.now() + offset * 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
      const slot = '15:00'
      if (date === ticket.bookingDate && slot === ticket.timeSlot) continue
      const availability = await call('GET', `/workshops/${ticket.workshop.workshopId}/availability?date=${date}&timeSlot=${slot}&rescheduleBookingId=${ticket.bookingId}`)
      if (availability.data?.requested?.confirmationToken) {
        token = availability.data.requested.confirmationToken
        chosen = { date, slot }
      }
    }
    expect(token).toBeTruthy()
    const moved = await call('POST', `/bookings/${ticket.bookingId}/reschedule`, { confirmationToken: token, source: 'APP' }, { 'Idempotency-Key': 'r1' })
    expect(moved.data).toMatchObject({ bookingId: ticket.bookingId, bookingCode: ticket.bookingCode, bookingDate: chosen!.date, rescheduleCount: 1 })
    const reused = await call('POST', `/bookings/${ticket.bookingId}/reschedule`, { confirmationToken: token, source: 'APP' })
    expect(reused.error.code).toBe('INVALID_CONFIRMATION_TOKEN')

    const cancelled = await call('POST', `/bookings/${ticket.bookingId}/cancel`, { source: 'REMINDER_24H', reason: 'Bận' }, { 'Idempotency-Key': 'c1' })
    expect(cancelled.data.status).toBe('CANCELLED')
    const twice = await call('POST', `/bookings/${ticket.bookingId}/cancel`, { source: 'APP' })
    expect(twice.status).toBe(200)
    const after = (await call('GET', `/bookings/${ticket.bookingId}`)).data
    expect(after.allowedActions).toEqual([])
    expect(after.qrPayload).toBeNull()
  })

  it('hides bookings of other owners and unknown codes (BR-713, EDGE-1208)', async () => {
    await call('GET', '/bookings')
    const other = getDb().bookings.find(item => !item.ownerSelf)!
    expect((await call('GET', `/bookings/${other.bookingId}`)).error.code).toBe('BOOKING_NOT_FOUND')
    expect((await call('GET', `/bookings/by-code/${other.bookingCode}`)).status).toBe(404)
  })
})

describe('us-041 follow-up', () => {
  it('records a low rating with a safety keyword as an issue with safety advice', async () => {
    await call('GET', '/bookings')
    const followUp = getDb().followUps.find(item => getDb().bookings.find(booking => booking.bookingId === item.bookingId)?.ownerSelf)!
    const answer = await call('POST', `/follow-ups/${followUp.followUpId}/response`, { rating: 2, comment: 'Phanh trước kêu khi dừng' })
    expect(answer.data.outcome).toMatchObject({ hasIssue: true, safetyAdvice: true })
    expect(answer.data.outcome).not.toHaveProperty('ticket')
    expect((await call('GET', '/support-tickets')).status).toBe(0) // no such route any more
    expect((await call('POST', `/follow-ups/${followUp.followUpId}/response`, { rating: 5 })).error.code).toBe('FOLLOW_UP_ALREADY_RESPONDED')
  })

  it('classifies satisfied answers without AI and complaints as issues (BR-906)', () => {
    expect(classify(5, null)).toMatchObject({ hasIssue: false, classifiedBy: 'RULES' })
    expect(classify(4, 'Xe chạy êm, nhân viên nhiệt tình')).toMatchObject({ hasIssue: false })
    expect(classify(3, 'Chờ lâu quá')).toMatchObject({ hasIssue: true, safety: false })
    expect(classify(1, null)).toMatchObject({ hasIssue: true })
    expect(classify(2, 'Có mùi khét ở khoang pin')).toMatchObject({ hasIssue: true, safety: true })
  })
})
