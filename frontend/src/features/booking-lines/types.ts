/** Two-tier booking pricing (docs/designs/bao-gia-hai-tang.md) — API shapes. */

export type LineKind = 'PACKAGE' | 'EXTRA'
export type LineStatus = 'PENDING_CONFIRM' | 'CONFIRMED' | 'PROPOSED' | 'APPROVED' | 'DECLINED' | 'WITHDRAWN'
export type PricingFlow = 'legacy' | 'two_tier'
export type Decision = 'APPROVE' | 'DECLINE'

export interface LinePhoto {
  photoId: string
  /** Signed, valid 10 minutes; null when the storage is unreachable. */
  url: string | null
}

export interface BookingLine {
  lineId: string
  kind: LineKind
  status: LineStatus
  itemCode: string | null
  itemName: string
  /** Price shown at booking time (package) or proposed by the workshop (extra). */
  unitPrice: number
  /** Price the workshop confirmed after check-in (package only). */
  confirmedPrice: number | null
  /** What the line costs once settled. */
  price: number
  priceSource: string | null
  /** "Giá xưởng" | "Giá tham khảo" | "Xưởng đã xác nhận" | "Bảo hành" | "Phát sinh" */
  priceLabel: string
  isCoveredByWarranty: boolean
  isSafetyCritical: boolean
  reason: string | null
  version: number
  confirmedAt: string | null
  decidedAt: string | null
  createdAt: string
  photos: LinePhoto[]
}

export interface BlockedAction {
  action: 'START' | 'COMPLETE'
  reasonCode: string
  message: string
}

export interface LinesView {
  bookingId: string
  bookingStatus: string
  pricingFlow: PricingFlow
  packageNotice: string | null
  lines: BookingLine[]
  currentTotal: number
  totalIfAllApproved: number
  pendingDecisionCount: number
  unconfirmedCount: number
  blockedActions: BlockedAction[]
}

export interface ProposeExtraRequest {
  itemCode?: string | null
  itemName?: string | null
  price: number
  reason: string
  isSafetyCritical: boolean
  photoKeys: string[]
}

export interface PhotoUploadTarget {
  key: string
  uploadUrl: string
  token: string | null
}
