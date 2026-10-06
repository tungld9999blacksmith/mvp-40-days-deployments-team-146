/** FEAT-CRM-001 types — API Spec us-041 (API-FU-01 → 02). */

export interface FollowUpOutcome {
  hasIssue: boolean
  safetyAdvice: boolean
  message?: string
  safetyMessage?: string | null
}

export interface FollowUp {
  followUpId: string
  status: 'PENDING' | 'SENT' | 'CLOSED'
  closedReason?: 'PROCESSED' | 'NO_RESPONSE' | null
  canRespond: boolean
  respondBefore?: string | null
  question: string
  booking: { bookingId: string; bookingCode: string | null; bookingDate: string }
  workshop: { name: string; hotline: string }
  response: { rating: number; comment: string | null; respondedAt: string } | null
  outcome: FollowUpOutcome | null
}

export interface FollowUpResult {
  followUpId: string
  status: 'CLOSED'
  outcome: FollowUpOutcome
}
