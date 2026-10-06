/** FEAT-PROG-001 types — API Spec us-057 (API-PG-01 → 03). */

export type Stage = 'CHECKED_IN' | 'INSPECTING' | 'SERVICING' | 'WAITING_PARTS' | 'QUALITY_CHECK' | 'READY_FOR_PICKUP'

export interface ProgressEntry {
  stage: Stage
  note: string | null
  actorType: 'SYSTEM' | 'WORKSHOP_OWNER'
  /** Portal only (API-PG-01); the owner app never gets who wrote it. */
  actorName?: string | null
  createdAt: string
}

export interface Progress {
  bookingId: string
  bookingStatus: string
  currentStage: Stage | null
  isFrozen: boolean
  /** Only from API-PG-01 (Portal). */
  nextStages?: Stage[]
  entries: ProgressEntry[]
}
