/**
 * Two-tier booking pricing — pure display rules (bao-gia-hai-tang design 1A, 6A, 8A,
 * 15A, 16A, 17A; re-review OV3, OV4, OV9). Tested with vitest; no React here.
 */
import { formatNumber, formatTime } from '@/shared/utils/format'
import type { BlockedAction, BookingLine, LinesView } from './types'

export const REASON_MIN = 10
export const REASON_MAX = 500
export const MAX_PHOTOS = 3
export const MAX_PHOTO_BYTES = 5 * 1024 * 1024
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const
export const PHOTO_RULE = 'Ảnh tối đa 5 MB, định dạng JPG/PNG/WebP'
export const POLL_MS = 15_000

/** "1.500.000 đồng" — spoken form for screen readers (15A). */
function spokenVnd(value: number): string {
  return `${formatNumber(value)} đồng`
}

// ── owner: "Cần bạn quyết định" (1A, 16A, OV4) ──────────────────────────────
export type DecisionResult = 'APPROVED' | 'DECLINED'

export interface DecisionCardView {
  /** hidden: no card; pending: lines to decide; summary: everything decided in this visit. */
  mode: 'hidden' | 'pending' | 'summary'
  /** Package lines whose price went up (shown first, 16A). */
  packageChanges: BookingLine[]
  extras: BookingLine[]
  /** Decisions made on this page since it loaded (OV4 summary). */
  decided: { lineId: string; itemName: string; price: number; result: DecisionResult }[]
}

export function decisionView(view: LinesView | null, decidedHere: Record<string, DecisionResult>): DecisionCardView {
  const lines = view?.lines ?? []
  const pending = lines.filter(line => line.status === 'PROPOSED')
  const decided = lines
    .filter(line => decidedHere[line.lineId] && (line.status === 'APPROVED' || line.status === 'DECLINED'))
    .map(line => ({ lineId: line.lineId, itemName: line.itemName, price: line.price, result: line.status as DecisionResult }))
  if (pending.length > 0) {
    return {
      mode: 'pending',
      packageChanges: pending.filter(line => line.kind === 'PACKAGE'),
      extras: pending.filter(line => line.kind === 'EXTRA'),
      decided,
    }
  }
  return { mode: decided.length > 0 ? 'summary' : 'hidden', packageChanges: [], extras: [], decided }
}

export function approveAriaLabel(line: BookingLine): string {
  return `Đồng ý ${line.itemName}, ${spokenVnd(line.price)}`
}

export function declineAriaLabel(line: BookingLine): string {
  return `${line.kind === 'PACKAGE' ? 'Không làm hạng mục này' : 'Không làm'}: ${line.itemName}, ${spokenVnd(line.price)}`
}

/** Owner total after approving `line`: what is settled now + this line. */
export function totalAfterApprove(view: LinesView, line: BookingLine): number {
  return view.currentTotal + line.price
}

/** 6A — what changed between the line on screen and the one the server returned. */
export function conflictNotice(before: BookingLine, after: BookingLine | undefined): string {
  if (!after || after.status === 'WITHDRAWN') return 'Xưởng đã rút hạng mục này.'
  if (after.status === 'APPROVED') return 'Bạn đã đồng ý hạng mục này ở một nơi khác.'
  if (after.status === 'DECLINED') return 'Bạn đã từ chối hạng mục này ở một nơi khác.'
  if (after.price !== before.price) return `Xưởng vừa đổi giá: ${formatNumber(before.price)} → ${formatNumber(after.price)} ₫. Xem lại rồi quyết định.`
  return 'Xưởng vừa cập nhật hạng mục này. Xem lại rồi quyết định.'
}

/** Line from a `LINE_CHANGED` error's `details.line` merged with what we had. */
export function lineFromConflict(before: BookingLine, details: Record<string, unknown> | null): BookingLine {
  const raw = (details?.line ?? null) as Partial<{ status: BookingLine['status']; price: number; version: number }> | null
  if (!raw) return before
  return { ...before, status: raw.status ?? before.status, price: raw.price ?? before.price, version: raw.version ?? before.version }
}

// ── workshop: confirm reference prices (2A, 17A) ────────────────────────────
export function reasonRequired(price: number | null, reference: number): boolean {
  return price !== null && price > reference
}

export function reasonError(reason: string, required: boolean): string | null {
  const length = reason.trim().length
  if (required && length < REASON_MIN) return `Lý do cần ít nhất ${REASON_MIN} ký tự`
  if (length > REASON_MAX) return `Lý do tối đa ${REASON_MAX} ký tự`
  return null
}

export function confirmButtonLabel(price: number | null, reference: number): string {
  return reasonRequired(price, reference) ? 'Gửi chủ xe duyệt' : 'Xác nhận giá'
}

export function parsePrice(raw: string): number | null {
  const digits = raw.replace(/\D/g, '')
  if (!digits) return null
  const value = Number(digits)
  return value > 999_999_999 ? null : value
}

export interface WorkshopLinesView {
  unconfirmed: BookingLine[]
  extras: BookingLine[]
  /** Package lines already priced (read only). */
  settledPackage: BookingLine[]
}

export function workshopLinesView(view: LinesView | null): WorkshopLinesView {
  const lines = view?.lines ?? []
  return {
    unconfirmed: lines.filter(line => line.kind === 'PACKAGE' && line.status === 'PENDING_CONFIRM'),
    extras: lines.filter(line => line.kind === 'EXTRA' || (line.kind === 'PACKAGE' && line.status === 'PROPOSED')),
    settledPackage: lines.filter(line => line.kind === 'PACKAGE' && line.status !== 'PENDING_CONFIRM' && line.status !== 'PROPOSED'),
  }
}

/** 4A / 9B — workshop wording of a line's state. */
export const WORKSHOP_LINE_STATUS: Record<BookingLine['status'], { label: string; tone: 'success' | 'warning' | 'error' | 'neutral' }> = {
  PENDING_CONFIRM: { label: 'Chờ xác nhận giá', tone: 'warning' },
  CONFIRMED: { label: 'Đã chốt', tone: 'success' },
  PROPOSED: { label: 'Chờ chủ xe', tone: 'warning' },
  APPROVED: { label: 'Đã đồng ý', tone: 'success' },
  DECLINED: { label: 'Không làm', tone: 'neutral' },
  WITHDRAWN: { label: 'Đã rút', tone: 'neutral' },
}

export const OWNER_LINE_STATUS: Record<BookingLine['status'], { label: string; tone: 'success' | 'warning' | 'error' | 'neutral' }> = {
  PENDING_CONFIRM: { label: 'Xưởng xác nhận khi nhận xe', tone: 'neutral' },
  CONFIRMED: { label: 'Đã chốt', tone: 'success' },
  PROPOSED: { label: 'Cần bạn quyết định', tone: 'warning' },
  APPROVED: { label: 'Đã đồng ý', tone: 'success' },
  DECLINED: { label: 'Không làm', tone: 'neutral' },
  WITHDRAWN: { label: 'Xưởng đã rút', tone: 'neutral' },
}

// ── board buttons (OV9) ─────────────────────────────────────────────────────
export function blockedReason(blocked: BlockedAction[] | undefined, action: string): string | null {
  return blocked?.find(item => item.action === action)?.message ?? null
}

// ── photos (8A, OV6) ────────────────────────────────────────────────────────
export type PhotoStatus = 'uploading' | 'done' | 'error'

export interface PhotoDraft {
  id: string
  file: File | null
  previewUrl: string | null
  status: PhotoStatus
  progress: number
  key: string | null
  error: string | null
}

export function validatePhoto(file: Pick<File, 'size' | 'type'>): string | null {
  if (!PHOTO_TYPES.includes(file.type as (typeof PHOTO_TYPES)[number]) || file.size > MAX_PHOTO_BYTES || file.size === 0) return PHOTO_RULE
  return null
}

export interface PhotoTileState {
  canAddMore: boolean
  uploading: boolean
  /** Why "Gửi chủ xe" is disabled because of the photos, or null. */
  blockSubmit: string | null
  keys: string[]
}

export function photoTileState(photos: PhotoDraft[]): PhotoTileState {
  const uploading = photos.some(photo => photo.status === 'uploading')
  const failed = photos.some(photo => photo.status === 'error')
  return {
    canAddMore: photos.length < MAX_PHOTOS,
    uploading,
    blockSubmit: uploading ? 'Chờ tải ảnh xong' : failed ? 'Tải lại hoặc xoá ảnh lỗi' : null,
    keys: photos.filter(photo => photo.status === 'done' && photo.key).map(photo => photo.key as string),
  }
}

// ── refresh while the car is at the workshop (OV3) ──────────────────────────
export function shouldPoll(bookingStatus: string | null | undefined, visible: boolean): boolean {
  return visible && (bookingStatus === 'CHECKED_IN' || bookingStatus === 'IN_PROGRESS')
}

/** Bookings with price lines waiting for the owner's decision (two_tier workshop dashboard). */
export function awaitingOwnerItems<T extends { awaitingOwner?: number; status: string }>(items: T[]): T[] {
  return items.filter(item => (item.awaitingOwner ?? 0) > 0 && item.status !== 'CANCELLED')
}

// ── decisions recorded by phone (TODOS P2, concern R2-2) ────────────────────
export const PHONE_NAME_MAX = 100

/** Phone decisions the owner can still dispute ("Tôi không đồng ý"). */
export function phoneDisputable(view: LinesView | null): BookingLine[] {
  return (view?.lines ?? []).filter(line => line.canDispute && line.decidedVia === 'PHONE')
}

/** Who answered the phone: required, 2-100 characters. */
export function phoneNameError(name: string): string | null {
  const length = name.trim().length
  if (length < 2) return 'Ghi tên người xác nhận qua điện thoại.'
  if (length > PHONE_NAME_MAX) return `Tối đa ${PHONE_NAME_MAX} ký tự.`
  return null
}

// ── owner reply SLA (open question 2): the workshop calls after 10 minutes ────
export const OWNER_REPLY_MINUTES = 10

export type ReplyState = { kind: 'none' } | { kind: 'waiting'; dueAt: string } | { kind: 'call' }

/** Where a line stands against the reply deadline; the server's callOwner wins over a slow client clock. */
export function replyState(line: Pick<BookingLine, 'status' | 'replyDueAt' | 'callOwner'>, now: number = Date.now()): ReplyState {
  if (line.status !== 'PROPOSED' || !line.replyDueAt) return { kind: 'none' }
  if (line.callOwner || now >= Date.parse(line.replyDueAt)) return { kind: 'call' }
  return { kind: 'waiting', dueAt: line.replyDueAt }
}

/** Workshop row: "Gọi chủ xe lúc 10:25 nếu chưa trả lời" / "Quá 10 phút chưa trả lời, gọi chủ xe". */
export function workshopReplyText(state: ReplyState): string | null {
  if (state.kind === 'waiting') return `Gọi chủ xe lúc ${formatTime(state.dueAt)} nếu chưa trả lời`
  if (state.kind === 'call') return `Quá ${OWNER_REPLY_MINUTES} phút chưa trả lời, gọi chủ xe`
  return null
}

/** Owner card: the earliest deadline among the lines still waiting for them. */
export function ownerReplyNotice(lines: BookingLine[], now: number = Date.now()): string | null {
  const states = lines.map(line => replyState(line, now))
  if (states.some(state => state.kind === 'call')) return 'Xưởng sẽ gọi cho bạn để hỏi ý kiến về các hạng mục chưa trả lời.'
  const due = states
    .flatMap(state => (state.kind === 'waiting' ? [state.dueAt] : []))
    .sort((a, b) => Date.parse(a) - Date.parse(b))[0]
  return due ? `Trả lời trước ${formatTime(due)}. Sau đó xưởng sẽ gọi cho bạn.` : null
}
