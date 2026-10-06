/** us-041 API-FU-01 → 02 — post-service follow-up. */
import { bodyOf, fail, ok, route } from './core'
import { getDb, maskPlate, nowIso, save, uuid, type MockBooking, type MockFollowUp } from './db'

const GROUP = 'crm'
const RESPONSE_WINDOW_HOURS = 72
/** Spec: 12 h after completion, outside quiet hours. The mock opens the survey after 1 minute for demos. */
export const FOLLOW_UP_DELAY_MINUTES = 1

function workshopOf(booking: MockBooking) {
  const workshop = getDb().workshops.find(item => item.workshopId === booking.workshopId)
  return { name: workshop?.name ?? 'Xưởng dịch vụ', hotline: workshop?.phone || '1900 23 23 89' }
}

function dayMonth(date: string): string {
  const [, month, day] = date.split('-')
  return `${day}/${month}`
}

export function scheduleFollowUp(booking: MockBooking, delayMinutes = FOLLOW_UP_DELAY_MINUTES): MockFollowUp {
  const db = getDb()
  const existing = db.followUps.find(item => item.bookingId === booking.bookingId)
  if (existing) return existing
  const followUp: MockFollowUp = {
    followUpId: uuid(),
    bookingId: booking.bookingId,
    status: 'pending',
    closedReason: null,
    scheduledAt: new Date(Date.now() + delayMinutes * 60_000).toISOString(),
    sentAt: null,
    question: `Xe ${booking.vehicle.modelName} (${maskPlate(booking.vehicle.licensePlate)}) đã bảo dưỡng xong tại ${workshopOf(booking).name} ngày ${dayMonth(booking.bookingDate)}. Xe của bạn chạy thế nào?`,
    response: null,
    outcome: null,
  }
  db.followUps.push(followUp)
  return followUp
}

/** JOB-FU-001 (send due) and JOB-FU-002 (close after 72 h), applied lazily. */
export function reconcileFollowUps() {
  let changed = false
  const now = Date.now()
  for (const followUp of getDb().followUps) {
    if (followUp.status === 'pending' && new Date(followUp.scheduledAt).getTime() <= now) {
      followUp.status = 'sent'
      followUp.sentAt = followUp.scheduledAt
      changed = true
    }
    if (followUp.status === 'sent' && followUp.sentAt && now > new Date(followUp.sentAt).getTime() + RESPONSE_WINDOW_HOURS * 3_600_000) {
      followUp.status = 'closed'
      followUp.closedReason = 'NO_RESPONSE'
      changed = true
    }
  }
  if (changed) save()
}

function plain(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
}

const SAFETY = ['phanh', 'pin', 'khoi', 'chay', 'mui khet', 'mat lai', 'den do', 'ro ri', 'canh bao']
const TECHNICAL = ['loi', 'keu', 'tieng la', 'rung', 'den bao', 'khong chay', 'sai', 'hong']
const SERVICE = ['lau', 'cho lau', 'dat qua', 'tinh tien', 'thai do', 'khong sach']

function hits(text: string, words: string[]): boolean {
  return words.some(word => new RegExp(`(^|[^a-z])${word}([^a-z]|$)`).test(text))
}

/** AI-007 stand-in: BR-906 rules + keyword fallback (API §4.3). */
export function classify(rating: number, comment: string | null) {
  if (rating >= 4 && !comment) {
    return { hasIssue: false, safety: false, intent: 'SATISFIED', confidence: 1, classifiedBy: 'RULES' as const }
  }
  const text = plain(comment ?? '')
  const safety = hits(text, SAFETY) && rating <= 3
  const technical = hits(text, TECHNICAL)
  const service = hits(text, SERVICE) && rating <= 3
  const hasIssue = rating <= 2 || safety || technical || service || (rating === 3 && Boolean(comment))
  const intent = safety ? 'SAFETY_CONCERN' : technical ? 'TECHNICAL_ISSUE' : service ? 'SERVICE_COMPLAINT' : hasIssue ? 'OTHER_ISSUE' : 'SATISFIED'
  return { hasIssue, safety: hasIssue && safety, intent, confidence: 0.86, classifiedBy: 'LLM' as const }
}

function outcomeView(booking: MockBooking, followUp: MockFollowUp) {
  if (!followUp.outcome) return null
  const workshop = workshopOf(booking)
  return {
    hasIssue: followUp.outcome.hasIssue,
    safetyAdvice: followUp.outcome.safetyAdvice,
    message: followUp.outcome.hasIssue
      ? `Cảm ơn bạn đã phản hồi. Chúng mình đã ghi nhận vấn đề bạn gặp. Nếu cần hỗ trợ, bạn hãy liên hệ xưởng ${workshop.name} qua số ${workshop.hotline}.`
      : `Cảm ơn bạn đã đánh giá dịch vụ tại ${workshop.name}. Chúc bạn có những chuyến đi an toàn!`,
    safetyMessage: followUp.outcome.safetyAdvice
      ? `Nếu xe có dấu hiệu bất thường khi vận hành, bạn nên dừng xe và liên hệ xưởng ngay: ${workshop.hotline}.`
      : null,
  }
}

function followUpView(booking: MockBooking, followUp: MockFollowUp) {
  const canRespond =
    followUp.status === 'sent' &&
    Boolean(followUp.sentAt) &&
    Date.now() <= new Date(followUp.sentAt!).getTime() + RESPONSE_WINDOW_HOURS * 3_600_000
  return {
    followUpId: followUp.followUpId,
    status: followUp.status.toUpperCase(),
    closedReason: followUp.closedReason,
    canRespond,
    respondBefore: followUp.sentAt ? new Date(new Date(followUp.sentAt).getTime() + RESPONSE_WINDOW_HOURS * 3_600_000).toISOString() : null,
    question: followUp.question,
    booking: { bookingId: booking.bookingId, bookingCode: booking.bookingCode, bookingDate: booking.bookingDate },
    workshop: workshopOf(booking),
    response: followUp.response,
    outcome: outcomeView(booking, followUp),
  }
}

function bookingOf(id: string): MockBooking | null {
  return getDb().bookings.find(item => item.bookingId === id) ?? null
}

const followUpNotFound = () => fail(404, 'FOLLOW_UP_NOT_FOUND', 'Không tìm thấy khảo sát.')

function ownFollowUp(id: string) {
  const followUp = getDb().followUps.find(item => item.followUpId === id)
  const booking = followUp ? bookingOf(followUp.bookingId) : null
  return followUp && booking?.ownerSelf ? { followUp, booking } : null
}

export function registerCrmRoutes() {
  route(GROUP, 'GET', '/follow-ups/:id', req => {
    const found = ownFollowUp(req.params.id)
    return found ? ok(followUpView(found.booking, found.followUp)) : followUpNotFound()
  })

  route(GROUP, 'POST', '/follow-ups/:id/response', async req => {
    const found = ownFollowUp(req.params.id)
    if (!found) return followUpNotFound()
    const { followUp, booking } = found
    const body = bodyOf<{ rating: number; comment: string | null }>(req)
    const rating = body.rating
    const comment = typeof body.comment === 'string' && body.comment.trim() ? body.comment.trim() : null
    if (!Number.isInteger(rating) || rating! < 1 || rating! > 5 || (comment?.length ?? 0) > 1000) {
      return fail(400, 'INVALID_REQUEST', 'Điểm 1–5, nhận xét tối đa 1000 ký tự.')
    }
    if (followUp.status === 'pending') return fail(409, 'FOLLOW_UP_NOT_OPEN', 'Chưa tới lúc đánh giá.')
    if (followUp.response) return fail(409, 'FOLLOW_UP_ALREADY_RESPONDED', 'Bạn đã gửi đánh giá.')
    if (followUp.status === 'closed' || !followUpView(booking, followUp).canRespond) {
      return fail(409, 'FOLLOW_UP_CLOSED', 'Khảo sát đã đóng.', { workshopHotline: workshopOf(booking).hotline })
    }
    // Classification takes a moment in the real backend (AI-007, ≤ 5 s).
    if (comment) await new Promise(resolve => setTimeout(resolve, 1200))
    const result = classify(rating!, comment)
    const now = nowIso()
    followUp.response = { rating: rating!, comment, respondedAt: now }
    followUp.outcome = { hasIssue: result.hasIssue, safetyAdvice: result.safety }
    followUp.status = 'closed'
    followUp.closedReason = 'PROCESSED'
    save()
    return ok({ followUpId: followUp.followUpId, status: 'CLOSED', outcome: outcomeView(booking, followUp) })
  })
}
