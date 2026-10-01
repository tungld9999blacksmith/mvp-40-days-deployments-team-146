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
  confirmationToken: string
  userVehicleId: string
  quoteId?: string
  milestoneRef?: string
  note?: string
}

/** `pending` (workshop confirms manually) or `confirmed` (auto mode). Backend sends lower case. */
export type BookingStatus = 'pending' | 'confirmed' | 'cancelled' | (string & {})

export interface Booking {
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
  quoteId: string | null
}

export interface CancelHoldData {
  bookingId: string
  status: BookingStatus
}
