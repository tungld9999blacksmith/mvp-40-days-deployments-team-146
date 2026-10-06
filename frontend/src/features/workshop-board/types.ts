/** FEAT-BOARD-001 types — API Spec us-037 (API-WB-01 → 08). */
import type { TicketStatus } from '@/features/bookings/types'

export type BoardAction = 'ACCEPT' | 'REJECT' | 'CHECK_IN' | 'START' | 'COMPLETE' | 'CANCEL'
export type BoardStatus = TicketStatus

export interface BoardItem {
  bookingId: string
  bookingCode: string | null
  status: BoardStatus
  bookingDate: string
  timeSlot: string
  customer: { fullName: string; phone: string }
  vehicle: { modelName: string; licensePlate: string }
  milestoneLabel: string | null
  estimatedCost: number | null
  attendanceConfirmedAt: string | null
  confirmDeadline: string | null
  allowedActions: BoardAction[]
}

export interface BoardData {
  workshopId: string | null
  confirmationMode: 'AUTO' | 'MANUAL'
  from: string
  to: string
  summary: Record<BoardStatus, number>
  items: BoardItem[]
}

export interface StatusEvent {
  fromStatus: string | null
  toStatus: string
  actorType: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM'
  source: string
  reasonCode: string | null
  note: string | null
  at: string
}

export interface BoardDetail extends BoardItem {
  actualCost: number | null
  note: string | null
  checkedInAt?: string | null
  currentStage?: string | null
  statusHistory: StatusEvent[]
}

export interface TransitionRequest {
  action: BoardAction
  expectedStatus: BoardStatus
  reasonCode?: string
  note?: string
  actualCost?: number
  source?: 'BOARD' | 'QR_SCAN'
}

/** API-WB-04 — only what changed; the caller merges it into the open detail and reloads. */
export interface TransitionResult extends Pick<BoardDetail, 'bookingId' | 'status' | 'allowedActions' | 'actualCost'> {
  effects: Record<string, unknown> | null
}

export type CheckInEligibility = 'ELIGIBLE' | 'NOT_TODAY' | 'ALREADY_CHECKED_IN' | 'NOT_CONFIRMED'

export interface CodeLookup extends BoardItem {
  checkInEligibility: CheckInEligibility
  checkedInAt: string | null
}

export interface CapacitySlot {
  timeSlot: string
  occupied: number
  blocked: number
  remaining: number
  maxBlock: number
  blockReason: string | null
  blockNote: string | null
}

export interface CapacityDay {
  date: string
  isClosed: boolean
  openTime: string | null
  closeTime: string | null
  slots: CapacitySlot[]
}

export interface CapacityData {
  totalTechnicians: number
  emergencySlotsReserved: number
  days: CapacityDay[]
}

export interface SlotBlockRequest {
  date: string
  timeSlot: string
  blockedCount: number
  reason?: string
  note?: string
}

export interface SlotBlockResult {
  date: string
  timeSlot: string
  blocked: number
  occupied: number
  remaining: number
  maxBlock: number
}

export interface BookingSettings {
  confirmationMode: 'AUTO' | 'MANUAL'
  wsConfirmDeadlineHours: number
  pendingCount: number
}
