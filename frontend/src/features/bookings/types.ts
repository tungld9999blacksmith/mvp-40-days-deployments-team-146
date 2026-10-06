/** FEAT-BOOK-001 types — backend `modules/booking/schemas.py`, API Spec us-029 (API-BK-01 → 04). */

export type AnchorSource = 'SPECIFIED' | 'PROFILE' | 'PREFERRED'
export type RankedBy = 'DISTANCE' | 'REGION'

export interface OperatingHours {
  isClosed: boolean
  /** `HH:mm:ss` */
  openTime: string | null
  closeTime: string | null
}

export interface SlotAvailability {
  date: string
  /** `HH:mm:ss` */
  timeSlot: string
  available: boolean
  remaining: number
  confirmationToken: string | null
}

export interface NearbyWorkshop {
  workshopId: string
  name: string
  address: string
  region: string
  /** `null` ⇒ ranked by region only ("Cùng khu vực"). */
  distanceKm: number | null
  isPreferred: boolean
  operatingHoursToday: OperatingHours | null
  availability: SlotAvailability | null
}

export interface NearbyAnchor {
  source: AnchorSource | string
  province: string | null
  lat: number | null
  lng: number | null
  query: string | null
  rankedBy: RankedBy | string
}

export interface NearbyData {
  anchor: NearbyAnchor
  workshops: NearbyWorkshop[]
}

/** Location the owner searches near. `null` ⇒ backend picks (profile, then preferred workshop). */
export type LocationAnchor =
  | { kind: 'query'; query: string }
  | { kind: 'coords'; lat: number; lng: number }
  | null

export interface Slot {
  timeSlot: string
  available: boolean
  remaining: number
}

export interface RequestedSlot extends Slot {
  confirmationToken: string | null
}

export interface Alternative {
  workshopId: string
  name: string
  date: string
  timeSlot: string
  remaining: number
}

export interface AvailabilityData {
  workshopId: string
  date: string
  requested: RequestedSlot | null
  slots: Slot[]
  alternatives: Alternative[]
}

export interface HoldRequest {
  proposalId?: string
  quoteId?: string
  confirmationToken: string
  userVehicleId: string
  milestoneRef?: string
  note?: string
}

/** `pending` (workshop confirms manually) or `confirmed` (auto mode). Backend sends lower case. */
export type BookingStatus = 'pending' | 'confirmed' | 'cancelled' | (string & {})

export interface Booking {
  quoteId?: string | null
  bookingId: string
  status: BookingStatus
  confirmationMode: string
  workshopId: string
  workshopName: string | null
  bookingDate: string
  timeSlot: string
  holdExpiresAt: string | null
  ownerCancelableUntil: string | null
  bookingCode: string | null
  qrUrl: string | null
  estimatedCost: string | number | null
  estimateLabel: string
}

export interface CancelHoldData {
  bookingId: string
  status: BookingStatus
}

// ---------------------------------------------------------------- us-033 / us-053 (ticket)

export type BookingAction = 'CONFIRM_ATTENDANCE' | 'CANCEL' | 'RESCHEDULE' | 'CANCEL_HOLD'
export type TicketStatus = 'PENDING' | 'CONFIRMED' | 'CHECKED_IN' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
export type RescheduleBlockedReason = 'TOO_CLOSE_TO_APPOINTMENT' | 'MAX_RESCHEDULES_REACHED' | 'NOT_CONFIRMED'

export type BookingHistoryEntry =
  | {
      kind: 'STATUS'
      fromStatus: string | null
      toStatus: string
      actorType: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM'
      source: string
      reasonCode: string | null
      note: string | null
      at: string
    }
  | {
      kind: 'RESCHEDULE'
      from: { date: string; timeSlot: string }
      to: { date: string; timeSlot: string }
      source: string
      at: string
    }

/** API-BR-01 extended with the us-053 ticket fields. */
export interface BookingDetail {
  bookingId: string
  bookingCode: string | null
  status: TicketStatus
  bookingDate: string
  timeSlot: string
  appointmentAt: string
  workshop: { workshopId: string; name: string; address: string | null; phone: string | null }
  vehicle: { userVehicleId: string | null; modelName: string; plateMasked: string }
  estimatedCost: number | null
  estimateLabel: string
  qrUrl: string | null
  qrPayload: string | null
  attendanceConfirmedAt: string | null
  allowedActions: BookingAction[]
  rescheduleMode: 'F6B' | 'GUIDE'
  rescheduleBlockedReason: RescheduleBlockedReason | null
  odoMilestone: number | null
  items: { itemName: string; covered: boolean }[]
  cost: { amount: number | null; label: 'ESTIMATE' | 'NONE' }
  documentsToBring: string[]
  rescheduleCount: number
  rescheduleDeadline: string | null
  holdExpiresAt: string | null
  ownerCancelableUntil: string | null
  cancelledAt: string | null
  cancelledBy: 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM' | null
  cancelReason: string | null
  completedAt: string | null
  history: BookingHistoryEntry[]
  /** us-041 §19 proposal: survey of a completed booking. */
  followUp: { followUpId: string; canRespond: boolean } | null
}

/** API-BT-01 row. */
export interface MyBookingItem {
  bookingId: string
  bookingCode: string | null
  status: TicketStatus
  appointmentAt: string
  bookingDate: string
  timeSlot: string
  workshop: { workshopId: string; name: string }
  cost: { amount: number | null; label: 'ESTIMATE' | 'NONE' }
  allowedActions: BookingAction[]
}

export interface MyBookingsPage {
  items: MyBookingItem[]
  nextCursor: string | null
}

export interface AttendanceResult {
  bookingId: string
  status: TicketStatus
  attendanceConfirmedAt: string
}

export interface CancelResult {
  bookingId: string
  status: 'CANCELLED'
  cancelledAt: string
  cancelledBy: 'VEHICLE_OWNER'
  source: string
}

export type BookingSource = 'APP' | 'REMINDER_24H'
