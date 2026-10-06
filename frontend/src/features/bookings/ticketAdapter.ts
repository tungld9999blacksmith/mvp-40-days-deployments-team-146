import type { BookingDetail, BookingHistoryEntry } from './types'

type ActorType = 'VEHICLE_OWNER' | 'WORKSHOP_OWNER' | 'SYSTEM'

/** API-BR-01 history row as the backend sends it (flat; `type` instead of `kind`). */
interface TicketHistoryDto {
  type: 'STATUS' | 'RESCHEDULE'
  at: string
  actorType: ActorType
  source: string
  fromStatus?: string | null
  toStatus?: string | null
  reasonCode?: string | null
  fromDate?: string | null
  fromTimeSlot?: string | null
  toDate?: string | null
  toTimeSlot?: string | null
}

/**
 * API-BR-01 / API-BT-04 payload. The backend sends the us-033 + us-053 ticket fields; the
 * cancel / completion summary, hold deadline and follow-up link are not part of that contract,
 * so they are derived from `history` here or left `null` (the ticket degrades without them).
 */
export type TicketDto = Omit<
  BookingDetail,
  'history' | 'holdExpiresAt' | 'ownerCancelableUntil' | 'cancelledAt' | 'cancelledBy' | 'cancelReason' | 'completedAt' | 'followUp'
> &
  Partial<Pick<BookingDetail, 'holdExpiresAt' | 'ownerCancelableUntil' | 'cancelledAt' | 'cancelledBy' | 'cancelReason' | 'completedAt' | 'followUp'>> & {
    history: (TicketHistoryDto | BookingHistoryEntry)[]
    actualCost?: number | null
  }

function toHistoryEntry(row: TicketHistoryDto | BookingHistoryEntry): BookingHistoryEntry {
  if ('kind' in row) return row // mock API already uses the UI shape
  if (row.type === 'RESCHEDULE') {
    return {
      kind: 'RESCHEDULE',
      from: { date: row.fromDate ?? '', timeSlot: row.fromTimeSlot ?? '' },
      to: { date: row.toDate ?? '', timeSlot: row.toTimeSlot ?? '' },
      source: row.source,
      at: row.at,
    }
  }
  return {
    kind: 'STATUS',
    fromStatus: row.fromStatus ?? null,
    toStatus: row.toStatus ?? '',
    actorType: row.actorType,
    source: row.source,
    reasonCode: row.reasonCode ?? null,
    note: null,
    at: row.at,
  }
}

/** Newest status event that moved the booking into `status` (history is newest first). */
function lastTransitionTo(history: BookingHistoryEntry[], status: string) {
  return history.find(
    (entry): entry is Extract<BookingHistoryEntry, { kind: 'STATUS' }> => entry.kind === 'STATUS' && entry.toStatus === status,
  )
}

export function toBookingDetail(dto: TicketDto): BookingDetail {
  dto = { ...dto, status: dto.status.toUpperCase() as BookingDetail['status'],
    qrPayload: dto.qrPayload ?? (dto.bookingCode ? `${typeof window === 'undefined' ? '' : window.location.origin}/c/${encodeURIComponent(dto.bookingCode)}` : null), attendanceConfirmedAt: dto.attendanceConfirmedAt ?? null,
    rescheduleMode: dto.rescheduleMode ?? 'GUIDE', rescheduleBlockedReason: dto.rescheduleBlockedReason ?? null,
    rescheduleCount: dto.rescheduleCount ?? 0, rescheduleDeadline: dto.rescheduleDeadline ?? null }
  const history = dto.history.map(toHistoryEntry)
  const cancelled = dto.status === 'CANCELLED' ? lastTransitionTo(history, 'CANCELLED') : undefined
  const completed = dto.status === 'COMPLETED' ? lastTransitionTo(history, 'COMPLETED') : undefined
  return {
    ...dto,
    cost: dto.actualCost !== null && dto.actualCost !== undefined ? { amount: dto.actualCost, label: 'ESTIMATE' } : dto.cost,
    estimateLabel: dto.actualCost !== null && dto.actualCost !== undefined ? 'Chi phí thực tế' : dto.estimateLabel,
    history,
    holdExpiresAt: dto.holdExpiresAt ?? null,
    ownerCancelableUntil: dto.ownerCancelableUntil ?? null,
    cancelledAt: dto.cancelledAt ?? cancelled?.at ?? null,
    cancelledBy: dto.cancelledBy ?? cancelled?.actorType ?? null,
    cancelReason: dto.cancelReason ?? cancelled?.reasonCode ?? null,
    completedAt: dto.completedAt ?? completed?.at ?? null,
    followUp: dto.followUp ?? null,
  }
}
