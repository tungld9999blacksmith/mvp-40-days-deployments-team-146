/** FEAT-NOTI-001 — backend `modules/notification/schemas.py`, API-SPEC-NOTI-001 §C.5. */

export type NotificationChannel = 'ZALO' | 'TELEGRAM' | 'SMS' | 'EMAIL' | (string & {})
export type ChannelStatus = 'CONNECTED' | 'NOT_CONNECTED' | 'COMING_SOON' | (string & {})

export interface ChannelSetting {
  channel: NotificationChannel
  enabled: boolean
  available: boolean
  status: ChannelStatus
}

export interface NotificationSettings {
  sendScheduleAvailable?: boolean
  preferredSendTime?: string | null
  quietHours?: { start: string; end: string } | null
  timezone?: string
  personalizedRemindersEnabled?: boolean
  personalizationAvailable?: boolean
  personalizationMode?: 'off' | 'shadow' | 'on'
  personalizationPolicyVersion?: string
  personalizationConsentAt?: string | null
  remindersEnabled: boolean
  reminderLeadDays: number
  defaultReminderLeadDays: number
  channels: ChannelSetting[]
  emailRecipient?: string | null
  emailVerified?: boolean
  emailSuppressed?: boolean
  emailScope?: 'MAINTENANCE_REMINDER'
  scope?: 'ALL_OWNED_VEHICLES'
  emailTransport?: 'mock' | 'resend' | 'resend_test' | 'off'
  emailTestRecipientMatched?: boolean | null
  emailTestManualOnly?: boolean
}

export interface NotificationSettingsUpdate {
  preferredSendTime?: string | null
  quietHours?: { start: string; end: string } | null
  timezone?: string
  personalizedRemindersEnabled?: boolean
  personalizationPolicyVersion?: string
  remindersEnabled?: boolean
  reminderLeadDays?: number
  channels?: { channel: NotificationChannel; enabled: boolean }[]
}

/** Editable part of the settings kept by the form. */
export interface SettingsForm {
  preferredSendTimeEnabled: boolean
  preferredSendTime: string
  quietHoursEnabled: boolean
  quietHoursStart: string
  quietHoursEnd: string
  timezone: string
  personalizedRemindersEnabled: boolean
  remindersEnabled: boolean
  reminderLeadDays: string
  channels: Record<string, boolean>
}

// ── API-NOTI-003 in-app feed (derived from existing records, no read state) ──
export type NotificationKind = 'MAINTENANCE_REMINDER' | 'QUOTE_RESULT' | 'BOOKING_UPDATE' | 'BOOKING_REMINDER' | 'FOLLOW_UP' | 'BOOKING_LINE'

export interface NotificationItem {
  id: string
  kind: NotificationKind
  occurredAt: string
  /** Only a reviewed quote not opened yet, a survey waiting for an answer and an appointment reminder not acted on. */
  unread: boolean
  reminder: { userVehicleId: string; level: 'EARLY' | 'WARNING' | 'URGENT' | 'EXPIRED'; odoMilestoneKm: number; resolved: boolean; resolutionReason?: string | null } | null
  quote?: { quoteId: string; status: 'APPROVED' | 'REJECTED'; approvedTotal: number | string | null; workshopName: string | null } | null
  booking: {
    bookingId: string
    bookingCode: string
    status: 'CONFIRMED' | 'CANCELLED' | 'COMPLETED'
    reasonCode: string | null
    bookingDate: string
    timeSlot: string
    workshopName: string | null
  } | null
  /** us-033 24h appointment reminder (us-069 BR-1707). */
  bookingReminder?: { bookingId: string; bookingCode: string; bookingDate: string; timeSlot: string; workshopName: string | null } | null
  followUp: { followUpId: string; bookingId: string; workshopName: string | null } | null
  /** Two-tier price line waiting for the owner, or a reference price the workshop confirmed (bao-gia-hai-tang). */
  bookingLine?: {
    bookingId: string
    bookingCode: string
    lineId: string
    kind: 'PACKAGE' | 'EXTRA'
    /** APPROVED / DECLINED only for a decision the workshop recorded by phone. */
    status: 'PROPOSED' | 'CONFIRMED' | 'APPROVED' | 'DECLINED'
    itemName: string
    price: number | string
    isSafetyCritical: boolean
    workshopName: string | null
    decidedVia?: 'APP' | 'PHONE' | null
    phoneConfirmedBy?: string | null
  } | null
}

export interface NotificationFeed {
  items: NotificationItem[]
  unreadCount: number
}

export interface ReminderContext {
  reminderId: string
  userVehicleId: string
  level: 'EARLY' | 'WARNING' | 'URGENT' | 'EXPIRED'
  odoMilestoneKm: number
  resolved: boolean
  resolutionReason: string | null
  snapshotAvailable?: boolean
  details: {
    trip?: { id: string; departureDate: string; returnDate: string | null; distanceKm: number; projectedTripEndKm: number | null }
    tripDeleted?: boolean
    personalization?: import('@/features/vehicles/types').MaintenanceForecast
    personalizationDeleted?: boolean
    triggerReasons?: string[]
    reason: 'KM' | 'TIME' | 'BOTH'
    dueDate: string
    monthMilestone: number | null
    remainingKm: number | null
    remainingDays: number | null
    odometerKm: number | null
    odometerRecordedAt: string | null
    odometerStale: boolean
    items: { itemCode: string; itemName: string }[]
  }
  currentStatus: import('@/features/vehicles/types').MaintenanceStatus
  hasCurrentBooking?: boolean
  deliveries: { id: string; channel?: string; status: string; deliveryState: string | null; attempts: number; errorCode: string | null; sentAt: string | null; nextEligibleSendAt?: string | null; mode?: string | null }[]
}

export interface DemoEmail {
  id: string
  reminderId: string
  status: string
  deliveryState: string | null
  attempts: number
  errorCode: string | null
  sentAt: string | null
  payload: { subject: string; body: string; html: string; link: string }
}
