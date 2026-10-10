import { describe, expect, it } from 'vitest'
import {
  approveAriaLabel,
  blockedReason,
  confirmButtonLabel,
  conflictNotice,
  decisionView,
  lineFromConflict,
  parsePrice,
  photoTileState,
  reasonError,
  reasonRequired,
  shouldPoll,
  validatePhoto,
  workshopLinesView,
  type PhotoDraft,
} from './logic'
import type { BookingLine, LinesView } from './types'

function line(overrides: Partial<BookingLine>): BookingLine {
  return {
    lineId: 'l1',
    kind: 'EXTRA',
    status: 'PROPOSED',
    itemCode: null,
    itemName: 'Thay má phanh trước',
    unitPrice: 1_500_000,
    confirmedPrice: null,
    price: 1_500_000,
    priceSource: null,
    priceLabel: 'Phát sinh',
    isCoveredByWarranty: false,
    isSafetyCritical: true,
    reason: 'Má phanh còn 2mm',
    version: 1,
    confirmedAt: null,
    decidedAt: null,
    createdAt: '2026-10-09T02:00:00Z',
    photos: [],
    ...overrides,
  }
}

function view(lines: BookingLine[]): LinesView {
  return {
    bookingId: 'b1',
    bookingStatus: 'IN_PROGRESS',
    pricingFlow: 'two_tier',
    packageNotice: null,
    lines,
    currentTotal: 300_000,
    totalIfAllApproved: 1_800_000,
    pendingDecisionCount: lines.filter(l => l.status === 'PROPOSED').length,
    unconfirmedCount: 0,
    blockedActions: [],
  }
}

function photo(overrides: Partial<PhotoDraft>): PhotoDraft {
  return { id: 'p', file: null, previewUrl: null, status: 'done', progress: 1, key: 'k', error: null, ...overrides }
}

describe('decisionView', () => {
  it('puts package price changes before extras and hides when nothing waits', () => {
    const pkg = line({ lineId: 'p1', kind: 'PACKAGE', unitPrice: 250_000, price: 300_000 })
    const extra = line({ lineId: 'e1' })
    const shown = decisionView(view([extra, pkg]), {})
    expect(shown.mode).toBe('pending')
    expect(shown.packageChanges.map(l => l.lineId)).toEqual(['p1'])
    expect(shown.extras.map(l => l.lineId)).toEqual(['e1'])
    expect(decisionView(view([line({ status: 'CONFIRMED' })]), {}).mode).toBe('hidden')
  })

  it('keeps a summary after the last decision made on this page (OV4)', () => {
    const decided = decisionView(view([line({ status: 'APPROVED' })]), { l1: 'APPROVED' })
    expect(decided.mode).toBe('summary')
    expect(decided.decided).toEqual([{ lineId: 'l1', itemName: 'Thay má phanh trước', price: 1_500_000, result: 'APPROVED' }])
  })
})

describe('labels and conflicts', () => {
  it('reads the item and price aloud (15A)', () => {
    expect(approveAriaLabel(line({}))).toBe('Đồng ý Thay má phanh trước, 1.500.000 đồng')
  })

  it('explains what changed (6A)', () => {
    const before = line({})
    expect(conflictNotice(before, line({ price: 1_800_000, version: 2 }))).toContain('1.500.000 → 1.800.000')
    expect(conflictNotice(before, line({ status: 'WITHDRAWN' }))).toBe('Xưởng đã rút hạng mục này.')
    expect(conflictNotice(before, undefined)).toBe('Xưởng đã rút hạng mục này.')
    expect(conflictNotice(before, line({ status: 'APPROVED' }))).toContain('đã đồng ý')
    expect(lineFromConflict(before, { line: { status: 'PROPOSED', price: 9, version: 3 } })).toMatchObject({ price: 9, version: 3 })
  })
})

describe('workshop pricing', () => {
  it('needs a reason only above the reference price (17A)', () => {
    expect(reasonRequired(300_000, 250_000)).toBe(true)
    expect(reasonRequired(250_000, 250_000)).toBe(false)
    expect(reasonRequired(null, 250_000)).toBe(false)
    expect(confirmButtonLabel(300_000, 250_000)).toBe('Gửi chủ xe duyệt')
    expect(confirmButtonLabel(200_000, 250_000)).toBe('Xác nhận giá')
    expect(reasonError('ngắn', true)).toBe('Lý do cần ít nhất 10 ký tự')
    expect(reasonError('', false)).toBeNull()
    expect(reasonError('x'.repeat(501), false)).toBe('Lý do tối đa 500 ký tự')
  })

  it('parses VND input', () => {
    expect(parsePrice('1.250.000')).toBe(1_250_000)
    expect(parsePrice('')).toBeNull()
    expect(parsePrice('9999999999')).toBeNull()
  })

  it('splits lines for the workshop card', () => {
    const split = workshopLinesView(
      view([
        line({ lineId: 'a', kind: 'PACKAGE', status: 'PENDING_CONFIRM' }),
        line({ lineId: 'b', kind: 'PACKAGE', status: 'PROPOSED' }),
        line({ lineId: 'c', kind: 'PACKAGE', status: 'CONFIRMED' }),
        line({ lineId: 'd', kind: 'EXTRA', status: 'WITHDRAWN' }),
      ]),
    )
    expect(split.unconfirmed.map(l => l.lineId)).toEqual(['a'])
    expect(split.extras.map(l => l.lineId)).toEqual(['b', 'd'])
    expect(split.settledPackage.map(l => l.lineId)).toEqual(['c'])
  })

  it('finds why a board action is blocked (OV9)', () => {
    const blocked = [{ action: 'START' as const, reasonCode: 'BOOKING_LINES_UNCONFIRMED', message: 'Còn 2 dòng chưa xác nhận giá' }]
    expect(blockedReason(blocked, 'START')).toBe('Còn 2 dòng chưa xác nhận giá')
    expect(blockedReason(blocked, 'COMPLETE')).toBeNull()
  })
})

describe('photos (8A)', () => {
  it('rejects big or unsupported files', () => {
    expect(validatePhoto({ size: 6 * 1024 * 1024, type: 'image/jpeg' })).toContain('5 MB')
    expect(validatePhoto({ size: 100, type: 'image/gif' })).toContain('JPG/PNG/WebP')
    expect(validatePhoto({ size: 100, type: 'image/webp' })).toBeNull()
  })

  it('blocks sending while a photo uploads and hides "add" at three', () => {
    expect(photoTileState([photo({ status: 'uploading', key: null })]).blockSubmit).toBe('Chờ tải ảnh xong')
    expect(photoTileState([photo({ status: 'error', key: null })]).blockSubmit).toBe('Tải lại hoặc xoá ảnh lỗi')
    const full = photoTileState([photo({ key: 'a' }), photo({ key: 'b' }), photo({ key: 'c' })])
    expect(full.canAddMore).toBe(false)
    expect(full.keys).toEqual(['a', 'b', 'c'])
    expect(photoTileState([]).blockSubmit).toBeNull()
  })
})

describe('shouldPoll (OV3)', () => {
  it('polls only while the car is at the workshop and the tab is visible', () => {
    expect(shouldPoll('CHECKED_IN', true)).toBe(true)
    expect(shouldPoll('IN_PROGRESS', true)).toBe(true)
    expect(shouldPoll('IN_PROGRESS', false)).toBe(false)
    expect(shouldPoll('COMPLETED', true)).toBe(false)
  })
})
