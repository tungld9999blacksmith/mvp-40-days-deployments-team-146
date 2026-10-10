/** us-049 API-QT-01 → 05 (owner) and API-QT-11 → 14 (Workshop Portal). */
import { estimate, hasRules, isValidMilestone, milestonesFor } from './catalog'
import { bodyOf, fail, noContent, ok, route, type MockRequest, type MockResult } from './core'
import { getDb, nowIso, save, uuid, type MockQuote, type MockVehicle } from './db'
import { canAttachToBooking, displayStatusOf, priceLabelOf } from './quoteRules'

const GROUP = 'quotes'
const DEFAULT_VALIDITY_DAYS = 7
const MAX_VALIDITY_DAYS = 30
const DRAFT_REFRESH_HOURS = 24
const DRAFT_TTL_DAYS = 7
const WAITING_LONG_HOURS = 24

function workshopName(id: string): string {
  return getDb().workshops.find(item => item.workshopId === id)?.name ?? 'Xưởng dịch vụ'
}

function detail(quote: MockQuote) {
  return {
    quoteId: quote.quoteId,
    status: quote.status.toUpperCase(),
    displayStatus: displayStatusOf(quote),
    workshop: { workshopId: quote.workshopId, name: workshopName(quote.workshopId) },
    userVehicleId: quote.userVehicleId,
    odoMilestone: quote.odoMilestone,
    items: quote.items,
    estimatedTotal: quote.estimatedTotal,
    approvedTotal: quote.approvedTotal,
    priceLabel: priceLabelOf(quote),
    createdAt: quote.createdAt,
    submittedAt: quote.submittedAt,
    reviewedAt: quote.reviewedAt,
    expiresAt: quote.expiresAt,
    reviewerNote: quote.reviewerNote,
    bookingId: quote.bookingId,
    canAttachToBooking: canAttachToBooking(quote),
    draftExpiresAt:
      quote.status === 'draft' ? new Date(new Date(quote.createdAt).getTime() + DRAFT_TTL_DAYS * 86_400_000).toISOString() : null,
  }
}

function waitingHours(quote: MockQuote): number {
  if (!quote.submittedAt) return 0
  const end = quote.reviewedAt ? new Date(quote.reviewedAt).getTime() : Date.now()
  return Math.floor((end - new Date(quote.submittedAt).getTime()) / 3_600_000)
}

function portalItem(quote: MockQuote) {
  const hours = waitingHours(quote)
  return {
    quoteId: quote.quoteId,
    displayStatus: displayStatusOf(quote),
    customer: quote.customer,
    modelName: quote.vehicle.modelName,
    plateNumber: quote.vehicle.licensePlate,
    odoMilestone: quote.odoMilestone,
    estimatedTotal: quote.estimatedTotal,
    approvedTotal: quote.approvedTotal,
    submittedAt: quote.submittedAt,
    reviewedAt: quote.reviewedAt,
    waitingHours: hours,
    isWaitingLong: quote.status === 'pending_approval' && hours >= WAITING_LONG_HOURS,
    hasConversation: quote.hasConversation,
  }
}

function snapshot(vehicle: MockVehicle, workshopId: string, odoMilestone: number) {
  const workshop = getDb().workshops.find(item => item.workshopId === workshopId)!
  const est = estimate(vehicle, odoMilestone, workshop, 'REQUEST')
  return {
    items: est.items.map(item => ({
      quoteItemId: uuid(),
      itemCode: item.itemCode,
      itemName: item.itemName,
      covered: item.covered,
      priceSource: item.priceSource,
      estimatedPrice: item.price,
      approvedPrice: null,
      reviewerNote: null,
    })),
    estimatedTotal: est.chargeableTotal,
  }
}

/** Builds a quote straight from the estimate service (BR-1101: never from client prices). */
export function newQuote(
  vehicle: MockVehicle,
  workshopId: string,
  odoMilestone: number,
  options: { ownerSelf: boolean; customer: { fullName: string; phone: string } },
): MockQuote {
  return {
    quoteId: uuid(),
    status: 'draft',
    userVehicleId: vehicle.userVehicleId,
    workshopId,
    odoMilestone,
    ownerSelf: options.ownerSelf,
    customer: options.customer,
    vehicle: { modelName: vehicle.modelName, licensePlate: vehicle.licensePlate },
    ...snapshot(vehicle, workshopId, odoMilestone),
    approvedTotal: null,
    createdAt: nowIso(),
    submittedAt: null,
    reviewedAt: null,
    expiresAt: null,
    reviewerNote: null,
    bookingId: null,
    resultSeenAt: null,
    hasConversation: false,
  }
}

function ownQuote(id: string): MockQuote | null {
  return getDb().quotes.find(quote => quote.quoteId === id && quote.ownerSelf) ?? null
}

function portalQuote(id: string): MockQuote | null {
  return getDb().quotes.find(quote => quote.quoteId === id && quote.status !== 'draft') ?? null
}

const notFound = () => fail(404, 'QUOTE_NOT_FOUND', 'Không tìm thấy báo giá.')

function remember(req: MockRequest, result: MockResult): MockResult {
  const key = req.headers.get('Idempotency-Key')
  if (key) {
    getDb().idempotency[`${req.path}:${key}`] = { status: result.status, body: result.body }
    save()
  }
  return result
}

/** Drafts older than the TTL are purged (JOB-QT-01, BR-1112). */
export function purgeStaleDrafts() {
  const db = getDb()
  const before = db.quotes.length
  db.quotes = db.quotes.filter(quote => quote.status !== 'draft' || Date.now() - new Date(quote.createdAt).getTime() < DRAFT_TTL_DAYS * 86_400_000)
  if (db.quotes.length !== before) save()
}

export function registerQuoteRoutes() {
  route(GROUP, 'POST', '/quotes', req => {
    const { userVehicleId, workshopId, odoMilestone } = bodyOf<{ userVehicleId: string; workshopId: string; odoMilestone: number }>(req)
    if (!userVehicleId || !workshopId || typeof odoMilestone !== 'number') return fail(400, 'INVALID_REQUEST', 'Thiếu thông tin báo giá.')
    const db = getDb()
    const vehicle = db.vehicles.find(item => item.userVehicleId === userVehicleId)
    if (!vehicle) return fail(404, 'VEHICLE_NOT_FOUND', 'Không tìm thấy xe.')
    const workshop = db.workshops.find(item => item.workshopId === workshopId)
    if (!workshop || !workshop.active) return fail(422, 'WORKSHOP_INACTIVE', 'Xưởng hiện không nhận khách.')
    if (!hasRules(vehicle)) return fail(422, 'NO_MAINTENANCE_RULE', 'Chưa có định mức bảo dưỡng cho mẫu xe này.')
    if (!isValidMilestone(vehicle, odoMilestone)) {
      return fail(422, 'NO_MAINTENANCE_RULE', 'Mốc bảo dưỡng không có trong định mức.', {
        validMilestones: milestonesFor(vehicle).map(item => item.odoMilestone),
      })
    }
    const quote = newQuote(vehicle, workshopId, odoMilestone, { ownerSelf: true, customer: { ...db.owner } })
    db.quotes.push(quote)
    save()
    return ok(detail(quote), 201)
  })

  route(GROUP, 'GET', '/quotes', req => {
    const statuses = req.query.getAll('status').map(item => item.toUpperCase())
    const vehicleId = req.query.get('userVehicleId')
    const unseen = req.query.get('unseenResult') === 'true'
    const limit = Math.min(Math.max(Number(req.query.get('limit') ?? 20) || 20, 1), 50)
    const offset = Number(req.query.get('cursor') ?? 0) || 0
    const list = getDb()
      .quotes.filter(quote => quote.ownerSelf)
      .filter(quote => !vehicleId || quote.userVehicleId === vehicleId)
      .filter(quote => statuses.length === 0 || statuses.includes(displayStatusOf(quote)))
      .filter(quote => !unseen || ((quote.status === 'approved' || quote.status === 'rejected') && !quote.resultSeenAt))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    const page = list.slice(offset, offset + limit).map(quote => ({
      ...detail(quote),
      resultSeen: quote.resultSeenAt !== null,
    }))
    return ok({ items: page, nextCursor: offset + limit < list.length ? String(offset + limit) : null })
  })

  route(GROUP, 'GET', '/quotes/:id', req => {
    const quote = ownQuote(req.params.id)
    if (!quote) return notFound()
    if ((quote.status === 'approved' || quote.status === 'rejected') && !quote.resultSeenAt) {
      quote.resultSeenAt = nowIso()
      save()
    }
    return ok(detail(quote))
  })

  route(GROUP, 'POST', '/quotes/:id/submit', req => {
    const key = req.headers.get('Idempotency-Key')
    const stored = key ? getDb().idempotency[`${req.path}:${key}`] : undefined
    if (stored) return { status: stored.status, body: stored.body }
    const quote = ownQuote(req.params.id)
    if (!quote) return notFound()
    if (quote.status !== 'draft') return fail(409, 'QUOTE_NOT_DRAFT', 'Báo giá không còn là nháp.')
    const db = getDb()
    const workshop = db.workshops.find(item => item.workshopId === quote.workshopId)
    if (!workshop || !workshop.active) return fail(422, 'WORKSHOP_INACTIVE', 'Xưởng hiện không nhận khách.')
    const vehicle = db.vehicles.find(item => item.userVehicleId === quote.userVehicleId)
    if (vehicle && Date.now() - new Date(quote.createdAt).getTime() > DRAFT_REFRESH_HOURS * 3_600_000) {
      const fresh = snapshot(vehicle, quote.workshopId, quote.odoMilestone)
      quote.createdAt = nowIso()
      if (fresh.estimatedTotal !== quote.estimatedTotal) {
        Object.assign(quote, fresh)
        save()
        return fail(409, 'QUOTE_DRAFT_REFRESHED', 'Giá đã được cập nhật theo bảng giá mới.')
      }
    }
    const duplicate = db.quotes.find(
      other =>
        other.quoteId !== quote.quoteId &&
        other.status === 'pending_approval' &&
        other.userVehicleId === quote.userVehicleId &&
        other.workshopId === quote.workshopId &&
        other.odoMilestone === quote.odoMilestone,
    )
    if (duplicate) return fail(409, 'QUOTE_ALREADY_PENDING', 'Bạn đã gửi báo giá này cho xưởng.', { pendingQuoteId: duplicate.quoteId })
    quote.status = 'pending_approval'
    quote.submittedAt = nowIso()
    save()
    return remember(req, ok(detail(quote)))
  })

  route(GROUP, 'DELETE', '/quotes/:id', req => {
    const quote = ownQuote(req.params.id)
    if (!quote) return notFound()
    if (quote.status !== 'draft') return fail(409, 'QUOTE_NOT_DRAFT', 'Chỉ xoá được báo giá nháp.')
    const db = getDb()
    db.quotes = db.quotes.filter(item => item.quoteId !== quote.quoteId)
    save()
    return noContent()
  })

  // ------------------------------------------------------------ Workshop Portal

  route(GROUP, 'GET', '/workshop-owner/quotes', req => {
    const status = (req.query.get('status') ?? 'PENDING_APPROVAL').toUpperCase()
    const matches = (quote: MockQuote) => {
      const display = displayStatusOf(quote)
      if (status === 'APPROVED') return display === 'APPROVED' || display === 'MODIFIED' || display === 'EXPIRED'
      return display === status
    }
    const list = getDb().quotes.filter(quote => quote.status !== 'draft' && matches(quote))
    list.sort((a, b) =>
      status === 'PENDING_APPROVAL'
        ? (a.submittedAt ?? '').localeCompare(b.submittedAt ?? '')
        : (b.reviewedAt ?? '').localeCompare(a.reviewedAt ?? ''),
    )
    const counts = { PENDING_APPROVAL: 0, APPROVED: 0, REJECTED: 0 }
    for (const quote of getDb().quotes) {
      const display = displayStatusOf(quote)
      if (display === 'PENDING_APPROVAL') counts.PENDING_APPROVAL += 1
      else if (display === 'REJECTED') counts.REJECTED += 1
      else if (display !== 'DRAFT') counts.APPROVED += 1
    }
    return ok({ items: list.map(portalItem), summary: counts, nextCursor: null })
  })

  route(GROUP, 'GET', '/workshop-owner/quotes/:id', req => {
    const quote = portalQuote(req.params.id)
    if (!quote) return notFound()
    return ok({
      ...detail(quote),
      ...portalItem(quote),
      customer: quote.customer,
      conversationExcerptUrl: quote.hasConversation ? `/api/v1/workshop/quotes/${quote.quoteId}/conversation-excerpt` : null,
    })
  })

  route(GROUP, 'POST', '/workshop-owner/quotes/:id/approve', req => {
    const quote = portalQuote(req.params.id)
    if (!quote) return notFound()
    if (quote.status !== 'pending_approval') {
      return fail(409, 'QUOTE_ALREADY_REVIEWED', 'Báo giá đã được xử lý.', { status: displayStatusOf(quote) })
    }
    const body = bodyOf<{ validityDays: number; reviewerNote: string; items: { quoteItemId: string; approvedPrice: number; note?: string }[] }>(req)
    const validity = body.validityDays ?? DEFAULT_VALIDITY_DAYS
    if (!Number.isInteger(validity) || validity < 1 || validity > MAX_VALIDITY_DAYS) {
      return fail(400, 'INVALID_REQUEST', 'Thời hạn 1–30 ngày.', { field: 'validityDays' })
    }
    if ((body.reviewerNote ?? '').length > 500) return fail(400, 'INVALID_REQUEST', 'Ghi chú tối đa 500 ký tự.', { field: 'reviewerNote' })
    const edits = new Map((body.items ?? []).map(item => [item.quoteItemId, item]))
    for (const [id, edit] of edits) {
      const item = quote.items.find(line => line.quoteItemId === id)
      if (!item) return fail(400, 'INVALID_REQUEST', 'Dòng báo giá không hợp lệ.', { field: `items.${id}` })
      if (typeof edit.approvedPrice !== 'number' || edit.approvedPrice < 0) {
        return fail(400, 'INVALID_REQUEST', 'Giá duyệt không hợp lệ.', { field: `items.${id}` })
      }
      if (item.covered && edit.approvedPrice !== 0) {
        return fail(422, 'COVERED_ITEM_LOCKED', 'Không sửa giá dòng bảo hành.', { quoteItemId: id })
      }
    }
    for (const item of quote.items) {
      const edit = edits.get(item.quoteItemId)
      item.approvedPrice = edit ? edit.approvedPrice : item.estimatedPrice
      item.reviewerNote = edit?.note?.trim() || null
    }
    quote.approvedTotal = quote.items.reduce((sum, item) => sum + (item.approvedPrice ?? 0), 0)
    quote.status = 'approved'
    quote.reviewedAt = nowIso()
    quote.expiresAt = new Date(Date.now() + validity * 86_400_000).toISOString()
    quote.reviewerNote = body.reviewerNote?.trim() || null
    quote.resultSeenAt = null
    save()
    return ok({ ...detail(quote), ...portalItem(quote) })
  })

  route(GROUP, 'POST', '/workshop-owner/quotes/:id/reject', req => {
    const quote = portalQuote(req.params.id)
    if (!quote) return notFound()
    if (quote.status !== 'pending_approval') {
      return fail(409, 'QUOTE_ALREADY_REVIEWED', 'Báo giá đã được xử lý.', { status: displayStatusOf(quote) })
    }
    const note = (bodyOf<{ reviewerNote: string }>(req).reviewerNote ?? '').trim()
    if (note.length < 10 || note.length > 500) {
      return fail(422, 'REVIEWER_NOTE_REQUIRED', 'Lý do từ chối cần 10–500 ký tự.', { field: 'reviewerNote' })
    }
    quote.status = 'rejected'
    quote.reviewedAt = nowIso()
    quote.reviewerNote = note
    quote.resultSeenAt = null
    save()
    return ok({ ...detail(quote), ...portalItem(quote) })
  })
}
