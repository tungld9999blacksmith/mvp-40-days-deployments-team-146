import { ApiError, isApiError } from '@/shared/api/client'
import { newId } from '@/shared/utils/id'
import { createBooking, getAvailability, getBooking, getNearbyWorkshops, listMyBookings } from '@/features/bookings/api'
import type { Alternative, Booking, LocationAnchor, NearbyWorkshop } from '@/features/bookings/types'
import { addDays, todayVn } from '@/features/bookings/utils'
import { getCostEstimate } from '@/features/estimate/api'
import { getMaintenanceStatus, getVehicleProfile } from '@/features/vehicles/api'
import type { MaintenanceStatus } from '@/features/vehicles/types'
import { QUICK_BOOKING_LABEL } from '../quickBooking/proposalView'
import type {
  BookingProposalCard,
  ConfirmProposalResult,
  ConversationExcerpt,
  MessageDto,
  ProposalOption,
  ProposalStatus,
} from '../types'
import { appendMessage, conversations, getConversation, newMessage, registerMockChatSection, saveMockChat, type MockConversation } from './mockStore'

/**
 * us-061 quick booking for the mock chat transport: the API-QB-01 → 04 contract with the texts and
 * rules of backend `modules/quick_booking`. Slots, estimates and the booking go through the same
 * feature APIs as the app (the mock API in demo mode); nothing is booked before "Xác nhận đặt lịch".
 */

const MIN_LEAD_MS = 120 * 60_000 // BR-1504
const HORIZON_DAYS = 14
const NOT_DUE_LEAD_DAYS = 7
const MAX_LOOKAHEAD_DAYS = 60
const MAX_WORKSHOPS = 5
const MAX_ALTERNATIVES = 2
const PROPOSAL_TTL_MS = 30 * 60_000 // BR-1508
const WS_CONFIRM_DEADLINE_HOURS = 12
const OPEN_STATUSES = ['PENDING', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS']
const FALLBACK_REGIONS = ['Hà Nội', 'TP. Hồ Chí Minh']
const WEEKDAYS = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy']

interface MockProposal {
  conversationId: string
  card: BookingProposalCard
  status: ProposalStatus
  odoMilestone: number | null
  messageId: string | null
  booking: BookingProposalCard['booking']
  bookingResult: ConfirmProposalResult['booking'] | null
  resultMessage: MessageDto | null
  inFlight: boolean
}

const proposals = new Map<string, MockProposal>()
/** bookingId → proposalId, for the Workshop Portal excerpt (API-CHAT-007). */
const bookingProposals = new Map<string, string>()

registerMockChatSection('quickBooking', {
  save: () => ({
    proposals: [...proposals].map(([id, proposal]) => [id, { ...proposal, inFlight: false }]),
    bookings: [...bookingProposals],
  }),
  load: data => {
    proposals.clear()
    bookingProposals.clear()
    const saved = data as { proposals: [string, MockProposal][]; bookings: [string, string][] } | null
    for (const [id, proposal] of saved?.proposals ?? []) proposals.set(id, proposal)
    for (const [bookingId, proposalId] of saved?.bookings ?? []) bookingProposals.set(bookingId, proposalId)
  },
})

// ---------------------------------------------------------------- texts (backend quick_booking/domain.py)

function formatDay(day: string): string {
  const [year, month, date] = day.split('-')
  return `${WEEKDAYS[new Date(`${day}T12:00:00+07:00`).getUTCDay()]}, ${date}/${month}/${year}`
}

function formatSlot(day: string, timeSlot: string): string {
  return `${timeSlot.slice(0, 5)} ${formatDay(day)}`
}

function formatKm(value: number): string {
  return `${new Intl.NumberFormat('vi-VN').format(value)} km`
}

function dueText(day: string): string {
  const [year, month, date] = day.split('-')
  return `${date}/${month}/${year}`
}

function maskPlate(plate: string | null): string | null {
  if (!plate) return null
  return plate.length <= 5 ? plate : `${plate.slice(0, 3)}***${plate.slice(-2)}`
}

function reasonText(status: MaintenanceStatus, afterDue: boolean): string {
  const milestone = status.nextMilestone!
  const km = formatKm(milestone.odoMilestoneKm)
  const remainingKm = status.remainingKm
  const remainingDays = status.remainingDays ?? 0
  if (status.dueStatus === 'OVERDUE') {
    const parts: string[] = []
    if (remainingKm !== null && remainingKm < 0) parts.push(formatKm(-remainingKm))
    if (remainingDays < 0) parts.push(`${-remainingDays} ngày`)
    return `Xe đã quá mốc ${km}: quá ${parts.join(' / ') || 'hạn'}. Đề xuất khung giờ sớm nhất còn trống.`
  }
  const left = [...(remainingKm !== null ? [formatKm(Math.max(remainingKm, 0))] : []), `${Math.max(remainingDays, 0)} ngày`].join(' / ')
  if (status.dueStatus === 'DUE_SOON') {
    const tail = afterDue ? 'Không còn khung giờ trước hạn nên đề xuất khung sớm nhất sau ngày hạn.' : 'Đề xuất lịch trước hạn.'
    return `Xe còn ${left} tới mốc ${km} (hạn ${dueText(milestone.dueDate)}). ${tail}`
  }
  return `Xe chưa đến hạn: còn ${left} tới mốc ${km} (hạn ${dueText(milestone.dueDate)}). Đề xuất lịch gần hạn.`
}

function unknownText(reason: string | null): string {
  if (reason === 'OEM_DATA_NOT_SYNCED') {
    return 'Mình chưa có đủ dữ liệu xe từ hãng (số ODO, lịch sử bảo dưỡng) để xác định mốc bảo dưỡng. Hệ thống đang lấy dữ liệu, bạn thử lại sau ít phút nhé.'
  }
  if (reason === 'NO_MAINTENANCE_RULE') {
    return 'Dòng xe của bạn chưa có lịch bảo dưỡng trong hệ thống. Bạn liên hệ xưởng để được tư vấn mốc bảo dưỡng nhé.'
  }
  return 'Mình chưa xác định được mốc bảo dưỡng của xe. Bạn thử lại sau nhé.'
}

function tooFarText(status: MaintenanceStatus): string {
  const milestone = status.nextMilestone!
  const km = status.remainingKm !== null ? `${formatKm(status.remainingKm)} / ` : ''
  return `Xe chưa đến hạn bảo dưỡng: còn ${km}${status.remainingDays} ngày tới mốc ${formatKm(milestone.odoMilestoneKm)} (hạn ${dueText(milestone.dueDate)}). Ứng dụng sẽ nhắc bạn khi gần hạn.`
}

const NO_SLOT_TEXT =
  'Các xưởng gần bạn hiện không còn khung giờ phù hợp trong thời gian tới. Bạn nhắn ngày mong muốn để mình tìm khung giờ khác nhé.'

function resultText(booking: Booking): string {
  const where = `${booking.workshopName ?? 'xưởng'} lúc ${formatSlot(booking.bookingDate, booking.timeSlot)}`
  if (booking.status.toUpperCase() === 'CONFIRMED' && booking.bookingCode) {
    return `Đã đặt lịch thành công tại ${where}. Mã đặt lịch: ${booking.bookingCode}. Bạn mở vé lịch hẹn để xem mã QR check-in.`
  }
  return `Đã gửi yêu cầu đặt lịch tại ${where}. Xưởng sẽ xác nhận trong tối đa ${WS_CONFIRM_DEADLINE_HOURS} giờ; mã đặt lịch có sau khi xưởng xác nhận.`
}

// ---------------------------------------------------------------- slot window (BR-1504) and scan (BR-1507)

interface SlotWindow {
  earliest: number
  lastDay: string
  afterDue: boolean
}

function appointmentMs(day: string, timeSlot: string): number {
  return new Date(`${day}T${timeSlot.slice(0, 5)}:00+07:00`).getTime()
}

function windowDays(window: SlotWindow): string[] {
  const days: string[] = []
  for (let day = todayVn(new Date(window.earliest)); day <= window.lastDay; day = addDays(day, 1)) days.push(day)
  return days
}

function slotWindows(status: MaintenanceStatus, now: number): SlotWindow[] | null {
  const dueDate = status.nextMilestone!.dueDate
  const earliest = now + MIN_LEAD_MS
  const today = todayVn(new Date(now))
  const horizonEnd = addDays(today, HORIZON_DAYS)
  if (status.dueStatus === 'OVERDUE') return [{ earliest, lastDay: horizonEnd, afterDue: false }]
  if (status.dueStatus === 'DUE_SOON') {
    const windows: SlotWindow[] = []
    if (dueDate >= todayVn(new Date(earliest))) windows.push({ earliest, lastDay: dueDate < horizonEnd ? dueDate : horizonEnd, afterDue: false })
    if (dueDate < horizonEnd) windows.push({ earliest, lastDay: horizonEnd, afterDue: true })
    return windows
  }
  const startDay = addDays(dueDate, -NOT_DUE_LEAD_DAYS)
  if (startDay > addDays(today, MAX_LOOKAHEAD_DAYS)) return null
  return [{ earliest: Math.max(earliest, appointmentMs(startDay, '00:00')), lastDay: dueDate, afterDue: false }]
}

/** Free slots of a workshop inside the window, earliest first. */
async function freeSlots(workshopId: string, window: SlotWindow, count: number, after: number | null = null) {
  const found: { date: string; timeSlot: string }[] = []
  for (const date of windowDays(window)) {
    let slots
    try {
      slots = (await getAvailability({ workshopId, date })).slots
    } catch {
      return found // outside the booking horizon / workshop closed for good
    }
    for (const slot of slots) {
      const at = appointmentMs(date, slot.timeSlot)
      if (!slot.available || at < window.earliest || (after !== null && at <= after)) continue
      found.push({ date, timeSlot: slot.timeSlot.slice(0, 5) })
      if (found.length >= count) return found
    }
  }
  return found
}

function option(index: number, workshop: Pick<NearbyWorkshop, 'workshopId' | 'name' | 'address' | 'region' | 'isPreferred'>, distanceKm: number | null, date: string, timeSlot: string): ProposalOption {
  return {
    optionId: `opt-${index}`,
    workshopId: workshop.workshopId,
    workshopName: workshop.name,
    address: workshop.address || null,
    region: workshop.region || null,
    distanceKm,
    isPreferred: workshop.isPreferred,
    date,
    timeSlot,
    estimate: null,
  }
}

async function scan(ranked: NearbyWorkshop[], window: SlotWindow, withDistance: boolean): Promise<ProposalOption[]> {
  const wanted = 1 + MAX_ALTERNATIVES
  const firsts = await Promise.all(ranked.map(workshop => freeSlots(workshop.workshopId, window, 1)))
  const found: { workshop: NearbyWorkshop; date: string; timeSlot: string }[] = []
  ranked.forEach((workshop, index) => {
    const slot = firsts[index][0]
    if (slot && found.length < wanted) found.push({ workshop, ...slot })
  })
  if (found.length > 0 && found.length < wanted) {
    const first = found[0]
    const extra = await freeSlots(first.workshop.workshopId, window, wanted - found.length, appointmentMs(first.date, first.timeSlot))
    found.push(...extra.map(slot => ({ workshop: first.workshop, ...slot })))
  }
  return found.map((item, index) => option(index + 1, item.workshop, withDistance ? item.workshop.distanceKm : null, item.date, item.timeSlot))
}

async function withEstimates(userVehicleId: string, odoMilestone: number | null, options: ProposalOption[]): Promise<ProposalOption[]> {
  if (odoMilestone === null) return options
  const byWorkshop = new Map<string, Promise<ProposalOption['estimate']>>()
  for (const item of options) {
    if (item.estimate || byWorkshop.has(item.workshopId)) continue
    byWorkshop.set(
      item.workshopId,
      getCostEstimate(userVehicleId, { odoMilestone, workshopId: item.workshopId })
        .then(estimate =>
          estimate.status === 'READY'
            ? { chargeableTotal: String(estimate.chargeableTotal), hasReferencePrice: estimate.hasReferencePrice, coveredCount: estimate.coveredCount }
            : null,
        )
        .catch(() => null),
    )
  }
  return Promise.all(options.map(async item => ({ ...item, estimate: item.estimate ?? (await byWorkshop.get(item.workshopId)) ?? null })))
}

/** Areas with an active workshop (AF-1501). Read from the mock data when it is loaded. */
async function regions(): Promise<string[]> {
  try {
    const { getDb } = await import('@/mocks/server/db')
    const list = [...new Set(getDb().workshops.filter(workshop => workshop.active && workshop.region).map(workshop => workshop.region))]
    return list.length ? list.sort((a, b) => a.localeCompare(b, 'vi')) : FALLBACK_REGIONS
  } catch {
    return FALLBACK_REGIONS
  }
}

// ---------------------------------------------------------------- proposals

function supersedeOpenProposals(now: number) {
  for (const proposal of proposals.values()) {
    if (proposal.status !== 'PROPOSED') continue
    proposal.status = new Date(proposal.card.expiresAt).getTime() <= now ? 'EXPIRED' : 'SUPERSEDED'
  }
}

function createProposal(
  conversation: MockConversation,
  base: Omit<BookingProposalCard, 'proposalId' | 'primary' | 'alternatives' | 'expiresAt' | 'status' | 'booking'>,
  options: ProposalOption[],
  odoMilestone: number | null,
): MockProposal {
  const now = Date.now()
  supersedeOpenProposals(now)
  const proposalId = newId()
  const proposal: MockProposal = {
    conversationId: conversation.id,
    card: {
      ...base,
      proposalId,
      primary: options[0],
      alternatives: options.slice(1),
      expiresAt: new Date(now + PROPOSAL_TTL_MS).toISOString(),
      status: 'PROPOSED',
      booking: null,
    },
    status: 'PROPOSED',
    odoMilestone,
    messageId: null,
    booking: null,
    bookingResult: null,
    resultMessage: null,
    inFlight: false,
  }
  proposals.set(proposalId, proposal)
  return proposal
}

/** Saves the assistant message carrying the proposal card and links them. */
function sayWithCard(conversation: MockConversation, text: string, proposal: MockProposal, refs: MessageDto['refs'] = {}): MessageDto {
  const message = appendMessage(conversation, newMessage('assistant', text, { card: { ...proposal.card }, refs }))
  proposal.messageId = message.id
  saveMockChat()
  return message
}

function effectiveStatus(proposal: MockProposal): ProposalStatus {
  if (proposal.status === 'PROPOSED' && new Date(proposal.card.expiresAt).getTime() <= Date.now()) proposal.status = 'EXPIRED'
  return proposal.status
}

/** HOOK-QB-01 — the live proposal status and booking status on every read. */
export async function enrichMessage(message: MessageDto): Promise<MessageDto> {
  const card = message.card
  if (card?.type !== 'BOOKING_PROPOSAL' || typeof card.proposalId !== 'string') return message
  const proposal = proposals.get(card.proposalId)
  if (!proposal) return message
  let booking = proposal.booking
  if (booking) {
    try {
      const ticket = await getBooking(booking.bookingId)
      booking = { ...booking, status: ticket.status, bookingCode: ticket.status === 'PENDING' ? null : ticket.bookingCode }
      proposal.booking = booking
    } catch {
      // keep the last known booking state
    }
  }
  return { ...message, card: { ...card, status: effectiveStatus(proposal), booking } }
}

interface Reply {
  text: string
  card: MessageDto['card']
  refs: MessageDto['refs']
  proposal: MockProposal | null
}

/** API-QB-01 §4.2 steps 2–10 (also used when the owner asks to book in free chat — TOOL-QB-01). */
async function buildReply(
  conversation: MockConversation,
  request: { location: { lat: number; lng: number } | null; province: string | null },
): Promise<Reply> {
  const userVehicleId = conversation.userVehicleId
  // EF-1501 — BR-013: one open booking per vehicle.
  const upcoming = await listMyBookings('UPCOMING')
  const open = upcoming.items.find(item => OPEN_STATUSES.includes(item.status))
  if (open) {
    const code = open.status !== 'PENDING' && open.bookingCode ? ` ${open.bookingCode}` : ''
    return {
      text: `Xe đã có lịch hẹn${code} lúc ${formatSlot(open.bookingDate, open.timeSlot)} tại ${open.workshop.name}. Bạn xem hoặc đổi lịch ở vé lịch hẹn nhé.`,
      card: null,
      refs: { bookingId: open.bookingId },
      proposal: null,
    }
  }

  // BR-1502 — the milestone comes from the maintenance status only.
  const status = await getMaintenanceStatus(userVehicleId)
  if (status.dueStatus === 'UNKNOWN' || !status.nextMilestone) return { text: unknownText(status.unknownReason), card: null, refs: {}, proposal: null }

  // BR-1505 — device position, else the profile / chosen province.
  const anchor: LocationAnchor = request.location
    ? { kind: 'coords', ...request.location }
    : request.province
      ? { kind: 'query', query: request.province }
      : null
  let nearby
  try {
    nearby = await getNearbyWorkshops({ anchor, userVehicleId })
  } catch (error) {
    if (!isApiError(error, 'LOCATION_ANCHOR_REQUIRED')) throw error
    return needLocation(await regions(), null)
  }
  const basis = request.location ? 'DEVICE' : 'PROVINCE'
  const province = request.province ?? nearby.anchor.province
  const locationLabel = basis === 'PROVINCE' && province ? `Xưởng trong khu vực ${province}` : null
  if (nearby.workshops.length === 0) return needLocation(await regions(), locationLabel)

  const now = Date.now()
  const windows = slotWindows(status, now)
  if (!windows) return { text: tooFarText(status), card: null, refs: {}, proposal: null }

  // BR-1506 — nearest first, the favourite workshop is not pinned.
  const ranked = (request.location
    ? [...nearby.workshops].sort((a, b) => (a.distanceKm ?? Number.POSITIVE_INFINITY) - (b.distanceKm ?? Number.POSITIVE_INFINITY))
    : nearby.workshops
  ).slice(0, MAX_WORKSHOPS)
  let options: ProposalOption[] = []
  let afterDue = false
  for (const window of windows) {
    options = await scan(ranked, window, Boolean(request.location))
    if (options.length) {
      afterDue = window.afterDue
      break
    }
  }
  if (!options.length) return { text: NO_SLOT_TEXT, card: null, refs: {}, proposal: null }

  const milestone = status.nextMilestone
  const [vehicle, priced] = await Promise.all([getVehicleProfile(userVehicleId), withEstimates(userVehicleId, milestone.odoMilestoneKm, options)])
  const reason = reasonText(status, afterDue)
  const proposal = createProposal(
    conversation,
    {
      type: 'BOOKING_PROPOSAL',
      version: 1,
      vehicle: { userVehicleId, modelName: vehicle.modelName, trim: vehicle.trim, licensePlateMasked: maskPlate(vehicle.licensePlate) },
      milestone: {
        odoMilestoneKm: milestone.odoMilestoneKm,
        monthMilestone: milestone.monthMilestone,
        label: milestone.label,
        dueDate: milestone.dueDate,
        dueStatus: status.dueStatus,
        dueReason: status.dueReason,
        remainingKm: status.remainingKm,
        remainingDays: status.remainingDays,
        items: milestone.items,
      },
      reason,
      locationBasis: basis,
      locationLabel,
    },
    priced,
    milestone.odoMilestoneKm,
  )
  const primary = priced[0]
  return {
    text: `${reason} Đề xuất: ${primary.workshopName} lúc ${formatSlot(primary.date, primary.timeSlot)}. Bấm "Xác nhận đặt lịch" trên thẻ để đặt.`,
    card: proposal.card as unknown as MessageDto['card'],
    refs: {},
    proposal,
  }
}

function needLocation(list: string[], missing: string | null): Reply {
  const text = missing
    ? `Chưa có xưởng đang hoạt động ở khu vực bạn chọn (${missing.replace('Xưởng trong khu vực ', '')}). Bạn chọn khu vực khác nhé.`
    : 'Mình chưa biết vị trí của bạn. Bạn muốn bảo dưỡng ở khu vực nào?'
  return { text, card: { type: 'QUICK_BOOKING_NEED_LOCATION', version: 1, regions: list }, refs: {}, proposal: null }
}

/** Assistant answer of a booking request typed in the chat (TOOL-QB-01 stand-in). */
export async function proposeFromChat(conversation: MockConversation): Promise<{ text: string; card: MessageDto['card']; refs: MessageDto['refs']; link: (message: MessageDto) => void }> {
  const reply = await buildReply(conversation, { location: null, province: null })
  return {
    text: reply.text,
    card: reply.card,
    refs: reply.refs,
    link: message => {
      if (!reply.proposal) return
      reply.proposal.messageId = message.id
      saveMockChat()
    },
  }
}

// ---------------------------------------------------------------- errors

function qbError(status: number, code: string, message: string, details: Record<string, unknown> | null = null): ApiError {
  return new ApiError({ status, code, message, details })
}

function ownedProposal(conversationId: string, proposalId: string): MockProposal {
  getConversation(conversationId)
  const proposal = proposals.get(proposalId)
  if (!proposal || proposal.conversationId !== conversationId) throw qbError(404, 'PROPOSAL_NOT_FOUND', 'Proposal was not found.')
  return proposal
}

function requireActive(proposal: MockProposal) {
  const status = effectiveStatus(proposal)
  if (status === 'EXPIRED') throw qbError(409, 'PROPOSAL_EXPIRED', 'The proposal has expired.')
  if (status !== 'PROPOSED') throw qbError(409, 'PROPOSAL_INACTIVE', 'The proposal is no longer active.', { status })
}

// ---------------------------------------------------------------- API-QB-02 helpers

function confirmedResult(proposal: MockProposal, replayed: boolean): ConfirmProposalResult {
  return {
    proposalId: proposal.card.proposalId,
    status: 'CONFIRMED',
    booking: proposal.bookingResult!,
    message: proposal.resultMessage,
    replayed,
  }
}

/** BR-1511 — never books: offers what is still free as a new proposal, then always throws. */
async function slotFull(conversation: MockConversation, proposal: MockProposal, extra: Alternative[]): Promise<never> {
  const earliest = Date.now() + MIN_LEAD_MS
  const candidates: ProposalOption[] = []
  const seen = new Set<string>()
  const take = (item: ProposalOption) => {
    const key = `${item.workshopId}|${item.date}|${item.timeSlot}`
    if (seen.has(key) || candidates.length >= 1 + MAX_ALTERNATIVES) return
    seen.add(key)
    candidates.push(item)
  }
  const old = [proposal.card.primary, ...proposal.card.alternatives]
  for (const item of proposal.card.alternatives) {
    if (appointmentMs(item.date, item.timeSlot) < earliest) continue
    const check = await getAvailability({ workshopId: item.workshopId, date: item.date, timeSlot: item.timeSlot, withAlternatives: false }).catch(() => null)
    if (check?.requested?.available) take({ ...item })
  }
  for (const alt of extra) {
    if (appointmentMs(alt.date, alt.timeSlot) < earliest) continue
    const known = old.find(item => item.workshopId === alt.workshopId)
    take({
      ...option(0, { workshopId: alt.workshopId, name: alt.name, address: known?.address ?? '', region: known?.region ?? '', isPreferred: known?.isPreferred ?? false }, known?.distanceKm ?? null, alt.date, alt.timeSlot.slice(0, 5)),
      estimate: known?.estimate ?? null,
    })
  }

  proposal.status = 'SUPERSEDED'
  if (!candidates.length) {
    const message = appendMessage(conversation, newMessage('assistant', NO_SLOT_TEXT))
    throw qbError(409, 'PROPOSAL_SLOT_FULL', 'The time slot is full.', { proposalId: null, message })
  }
  const options = await withEstimates(
    conversation.userVehicleId,
    proposal.odoMilestone,
    candidates.map((item, index) => ({ ...item, optionId: `opt-${index + 1}` })),
  )
  const { proposalId: _id, primary: _p, alternatives: _a, expiresAt: _e, status: _s, booking: _b, ...base } = proposal.card
  const next = createProposal(conversation, base, options, proposal.odoMilestone)
  const text = `Khung giờ ${formatSlot(proposal.card.primary.date, proposal.card.primary.timeSlot)} vừa hết chỗ. Đề xuất mới: ${options[0].workshopName} lúc ${formatSlot(options[0].date, options[0].timeSlot)}. Bấm "Xác nhận đặt lịch" để đặt lại.`
  const message = await enrichMessage(sayWithCard(conversation, text, next))
  throw qbError(409, 'PROPOSAL_SLOT_FULL', 'The time slot is full.', { proposalId: next.card.proposalId, message })
}

// ---------------------------------------------------------------- transport methods

export async function quickBooking(
  conversationId: string,
  body: { clientMessageId: string; location: { lat: number; lng: number } | null; province: string | null },
): Promise<{ userMessage: MessageDto; assistantMessage: MessageDto; replayed: boolean }> {
  const conversation = getConversation(conversationId)
  const existingId = conversation.clientIds.get(body.clientMessageId)
  const existing = existingId ? conversation.messages.find(message => message.id === existingId) : undefined
  if (existing) {
    const reply = conversation.messages.find(message => message.refs.inReplyTo === existing.id)
    if (reply) return { userMessage: existing, assistantMessage: await enrichMessage(reply), replayed: true }
  }
  const userMessage = existing ?? appendMessage(conversation, newMessage('user', QUICK_BOOKING_LABEL))
  conversation.clientIds.set(body.clientMessageId, userMessage.id)
  conversation.title ??= QUICK_BOOKING_LABEL
  const reply = await buildReply(conversation, { location: body.location, province: body.province })
  const refs = { ...reply.refs, inReplyTo: userMessage.id }
  const assistantMessage = reply.proposal
    ? sayWithCard(conversation, reply.text, reply.proposal, refs)
    : appendMessage(conversation, newMessage('assistant', reply.text, { card: reply.card, refs }))
  return { userMessage, assistantMessage: await enrichMessage(assistantMessage), replayed: false }
}

export async function confirmProposal(conversationId: string, proposalId: string): Promise<ConfirmProposalResult> {
  const conversation = getConversation(conversationId)
  const proposal = ownedProposal(conversationId, proposalId)
  if (proposal.status === 'CONFIRMED') return confirmedResult(proposal, true)
  requireActive(proposal)
  if (proposal.inFlight) throw qbError(409, 'PROPOSAL_IN_PROGRESS', 'Another confirmation is running.')
  proposal.inFlight = true
  try {
    const { primary } = proposal.card
    if (appointmentMs(primary.date, primary.timeSlot) <= Date.now()) return await slotFull(conversation, proposal, [])
    let availability
    try {
      availability = await getAvailability({ workshopId: primary.workshopId, date: primary.date, timeSlot: primary.timeSlot, withAlternatives: true })
    } catch (error) {
      if (isApiError(error, 'WORKSHOP_NOT_FOUND') || isApiError(error, 'SLOT_OUT_OF_HOURS')) return await slotFull(conversation, proposal, [])
      throw error
    }
    const token = availability.requested?.available ? availability.requested.confirmationToken : null
    if (!token) return await slotFull(conversation, proposal, availability.alternatives)

    let booking: Booking
    try {
      booking = await createBooking(
        {
          confirmationToken: token,
          userVehicleId: conversation.userVehicleId,
          ...(proposal.odoMilestone !== null ? { milestoneRef: String(proposal.odoMilestone) } : {}),
        },
        `quick-booking-${proposalId}`,
      )
    } catch (error) {
      if (isApiError(error, 'OPEN_BOOKING_EXISTS')) {
        throw qbError(409, 'OPEN_BOOKING_EXISTS', 'The vehicle already has an open booking.', { bookingId: (error as ApiError).details?.bookingId ?? null })
      }
      if (isApiError(error, 'SLOT_FULL')) {
        const list = (error as ApiError).details?.alternatives
        return await slotFull(conversation, proposal, Array.isArray(list) ? (list as Alternative[]) : [])
      }
      throw error
    }

    const status = booking.status.toUpperCase()
    proposal.status = 'CONFIRMED'
    proposal.booking = { bookingId: booking.bookingId, bookingCode: status === 'PENDING' ? null : booking.bookingCode, status, ownerCancelableUntil: booking.ownerCancelableUntil }
    proposal.bookingResult = {
      bookingId: booking.bookingId,
      bookingCode: proposal.booking.bookingCode,
      status,
      confirmationMode: booking.confirmationMode,
      workshopName: booking.workshopName,
      bookingDate: booking.bookingDate,
      timeSlot: booking.timeSlot,
      ownerCancelableUntil: booking.ownerCancelableUntil,
    }
    proposal.resultMessage = appendMessage(conversation, newMessage('assistant', resultText(booking), { refs: { bookingId: booking.bookingId } }))
    bookingProposals.set(booking.bookingId, proposalId)
    saveMockChat()
    return confirmedResult(proposal, false)
  } finally {
    proposal.inFlight = false
  }
}

export async function reviseProposal(
  conversationId: string,
  proposalId: string,
  body: { workshopId: string; date: string; timeSlot: string },
): Promise<{ proposalId: string; message: MessageDto }> {
  const conversation = getConversation(conversationId)
  const proposal = ownedProposal(conversationId, proposalId)
  requireActive(proposal)
  const offered = [proposal.card.primary, ...proposal.card.alternatives]
  const same = offered.find(item => item.workshopId === body.workshopId)
  if (!same) throw qbError(422, 'REVISE_WORKSHOP_NOT_OFFERED', 'Only the workshops on the card can be chosen.')
  const timeSlot = body.timeSlot.slice(0, 5)
  if (appointmentMs(body.date, timeSlot) < Date.now() + MIN_LEAD_MS) throw qbError(422, 'SLOT_TOO_SOON', 'The time slot is too soon.')
  const availability = await getAvailability({ workshopId: body.workshopId, date: body.date, timeSlot, withAlternatives: true })
  if (!availability.requested?.available) {
    throw qbError(409, 'SLOT_FULL', 'The selected time slot is no longer available.', { alternatives: availability.alternatives })
  }
  const chosen = { ...same, date: body.date, timeSlot }
  const key = (item: ProposalOption) => `${item.workshopId}|${item.date}|${item.timeSlot}`
  const rest = offered.filter(item => key(item) !== key(chosen)).slice(0, MAX_ALTERNATIVES)
  const options = [chosen, ...rest].map((item, index) => ({ ...item, optionId: `opt-${index + 1}` }))
  const { proposalId: _id, primary: _p, alternatives: _a, expiresAt: _e, status: _s, booking: _b, ...base } = proposal.card
  const next = createProposal(conversation, base, options, proposal.odoMilestone)
  const text = `Đã cập nhật đề xuất: ${chosen.workshopName} lúc ${formatSlot(body.date, timeSlot)}. Bấm "Xác nhận đặt lịch" để đặt.`
  const message = await enrichMessage(sayWithCard(conversation, text, next))
  return { proposalId: next.card.proposalId, message }
}

export async function cancelProposal(conversationId: string, proposalId: string): Promise<{ proposalId: string; status: 'CANCELLED' }> {
  const proposal = ownedProposal(conversationId, proposalId)
  if (proposal.status === 'CANCELLED') return { proposalId, status: 'CANCELLED' }
  if (proposal.status === 'CONFIRMED') throw qbError(409, 'PROPOSAL_ALREADY_CONFIRMED', 'The proposal is already booked.')
  requireActive(proposal)
  proposal.status = 'CANCELLED'
  saveMockChat()
  return { proposalId, status: 'CANCELLED' }
}

/** API-CHAT-007 — the conversation up to the proposal card a booking came from. */
export function excerptForBooking(bookingId: string): ConversationExcerpt | null {
  const proposalId = bookingProposals.get(bookingId)
  const proposal = proposalId ? proposals.get(proposalId) : undefined
  const conversation = proposal ? conversations.get(proposal.conversationId) : undefined
  const source = proposal?.messageId ? conversation?.messages.find(message => message.id === proposal.messageId) : undefined
  if (!conversation || !source) return null
  return {
    source: { type: 'booking', id: bookingId, confirmedMessageId: source.id },
    messages: conversation.messages
      .filter(message => message.seq <= source.seq)
      .slice(-20)
      .map(({ id, seq, role, content, createdAt }) => ({ id, seq, role, content, createdAt })),
  }
}
