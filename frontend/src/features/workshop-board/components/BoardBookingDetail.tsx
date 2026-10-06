import { useState } from 'react'
import { AlarmClock, Car, CheckCircle2, FileText, LogIn, Phone, Play, User, XCircle } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import { ACTOR_LABEL, bookingStatusLabel, PORTAL_BOOKING_STATUS as BOOKING_STATUS, REASON_LABEL, SOURCE_LABEL } from '@/shared/domain/bookingLabels'
import { formatLicensePlate, formatTimeDayMonth } from '@/shared/utils/format'
import ConversationExcerptPanel from '@/features/assistant/components/ConversationExcerptPanel'
import { formatVnd } from '@/features/estimate/utils'
import { formatLongDay, slotLabel } from '@/features/bookings/utils'
import ProgressPanel from '@/features/progress/components/ProgressPanel'
import type { Stage } from '@/features/progress/types'
import type { BoardAction, BoardDetail } from '../types'
import { appointmentIso } from '../utils'
import { CompleteDialog, ReasonDialog } from './BoardDialogs'

/** "Hạn xác nhận HH:mm", red under one hour (§4.4). */
export function DeadlineBadge({ deadline }: { deadline: string }) {
  const urgent = new Date(deadline).getTime() - Date.now() < 3_600_000
  return (
    <Badge tone={urgent ? 'error' : 'warning'} icon={<AlarmClock className="w-3.5 h-3.5" />}>
      Hạn xác nhận {formatTimeDayMonth(deadline)}
    </Badge>
  )
}

/** us-037 §4.8 — status history in Vietnamese, oldest first. */
function StatusTimeline({ events }: { events: BoardDetail['statusHistory'] }) {
  return (
    <ol className="space-y-3">
      {events.map(event => (
        <li key={`${event.toStatus}-${event.at}`} className="flex gap-3 text-sm">
          <span className="w-2 h-2 rounded-full bg-emerald/60 mt-1.5 shrink-0" aria-hidden />
          <span>
            <span className="text-xs text-muted font-mono">{formatTimeDayMonth(event.at)}</span>
            <span className="text-foreground"> · {bookingStatusLabel(event.toStatus)}</span>
            <span className="text-muted">
              {' '}
              · {ACTOR_LABEL[event.actorType] ?? event.actorType}
              {event.source ? ` ${SOURCE_LABEL[event.source] ?? event.source}` : ''}
              {event.reasonCode ? ` · ${REASON_LABEL[event.reasonCode] ?? event.reasonCode}` : ''}
            </span>
            {event.note && <span className="block text-muted">"{event.note}"</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

const ACTION_BUTTONS: { action: BoardAction; label: string; variant: 'primary' | 'secondary' | 'danger'; icon: typeof CheckCircle2 }[] = [
  { action: 'ACCEPT', label: 'Chấp nhận', variant: 'primary', icon: CheckCircle2 },
  { action: 'CHECK_IN', label: 'Check-in', variant: 'primary', icon: LogIn },
  { action: 'START', label: 'Bắt đầu làm', variant: 'primary', icon: Play },
  { action: 'COMPLETE', label: 'Hoàn tất', variant: 'primary', icon: CheckCircle2 },
  { action: 'REJECT', label: 'Từ chối', variant: 'danger', icon: XCircle },
  { action: 'CANCEL', label: 'Huỷ lịch', variant: 'danger', icon: XCircle },
]

/** SCR-802 — detail + actions (only those in `allowedActions`) + progress + history. */
export default function BoardBookingDetail({
  detail,
  pendingAction,
  readOnly,
  dialogError,
  progressKey,
  onAction,
}: {
  detail: BoardDetail
  pendingAction: BoardAction | null
  readOnly: boolean
  dialogError: string | null
  progressKey: number
  onAction: (action: BoardAction, extra?: { reasonCode?: string; note?: string; actualCost?: number | null }) => Promise<boolean>
}) {
  const [dialog, setDialog] = useState<'REJECT' | 'CANCEL' | 'COMPLETE' | null>(null)
  const [stage, setStage] = useState<Stage | null>(null)
  const status = BOOKING_STATUS[detail.status]
  const appt = appointmentIso(detail.bookingDate, detail.timeSlot)

  async function run(action: BoardAction, extra?: Parameters<typeof onAction>[1]) {
    const ok = await onAction(action, extra)
    if (ok) setDialog(null)
  }

  return (
    <div className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-lg font-semibold text-foreground">{detail.bookingCode ?? '—'}</span>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
        {detail.attendanceConfirmedAt && <Badge tone="success">✓ Khách đã xác nhận đến</Badge>}
        {detail.confirmDeadline && <DeadlineBadge deadline={detail.confirmDeadline} />}
      </div>

      {!readOnly && detail.allowedActions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {ACTION_BUTTONS.filter(button => detail.allowedActions.includes(button.action)).map(({ action, label, variant, icon: Icon }) => (
            <Button
              key={action}
              variant={variant}
              size="sm"
              icon={<Icon className="w-4 h-4" />}
              loading={pendingAction === action}
              disabled={pendingAction !== null}
              onClick={() => {
                if (action === 'REJECT' || action === 'CANCEL' || action === 'COMPLETE') setDialog(action)
                else void run(action)
              }}
            >
              {label}
            </Button>
          ))}
        </div>
      )}

      <Card>
        <CardHeader title="Khách hàng & xe" icon={<User className="w-4 h-4 text-muted" />} />
        <InfoRow label="Khách" value={detail.customer.fullName} />
        <InfoRow
          label="Điện thoại"
          value={
            detail.customer.phone ? (
              <a href={`tel:${detail.customer.phone}`} className="inline-flex items-center gap-1 text-emerald hover:text-emerald-bright">
                <Phone className="w-3.5 h-3.5" /> {detail.customer.phone}
              </a>
            ) : (
              '—'
            )
          }
        />
        <InfoRow label="Xe" value={<span className="inline-flex items-center gap-1.5"><Car className="w-3.5 h-3.5 text-muted" />{detail.vehicle.modelName}</span>} />
        <InfoRow label="Biển số" value={formatLicensePlate(detail.vehicle.licensePlate)} mono />
      </Card>

      <Card>
        <CardHeader title="Lịch hẹn" icon={<FileText className="w-4 h-4 text-muted" />} />
        <InfoRow label="Thời gian" value={`${slotLabel(detail.timeSlot)} · ${formatLongDay(detail.bookingDate)}`} />
        {detail.milestoneLabel && <InfoRow label="Hạng mục" value={detail.milestoneLabel} />}
        <InfoRow label="Chi phí ước tính" value={detail.estimatedCost !== null ? formatVnd(detail.estimatedCost) : '—'} />
        {detail.actualCost !== null && <InfoRow label="Chi phí thực tế" value={formatVnd(detail.actualCost)} />}
        {detail.note && <p className="text-sm text-muted mt-3">Ghi chú của khách: "{detail.note}"</p>}
      </Card>

      <ProgressPanel bookingId={detail.bookingId} bookingStatus={detail.status} refreshKey={progressKey} onStageChange={setStage} />

      <ConversationExcerptPanel source={{ type: 'booking', id: detail.bookingId }} />

      <Card>
        <CardHeader title="Lịch sử trạng thái" />
        <StatusTimeline events={detail.statusHistory} />
      </Card>

      <ReasonDialog
        open={dialog === 'REJECT' || dialog === 'CANCEL'}
        mode={dialog === 'REJECT' ? 'REJECT' : 'CANCEL'}
        appointmentAt={appt}
        submitting={pendingAction === 'REJECT' || pendingAction === 'CANCEL'}
        serverError={dialogError}
        onClose={() => setDialog(null)}
        onConfirm={(reasonCode, note) => void run(dialog === 'REJECT' ? 'REJECT' : 'CANCEL', { reasonCode, ...(note ? { note } : {}) })}
      />
      <CompleteDialog
        open={dialog === 'COMPLETE'}
        plate={formatLicensePlate(detail.vehicle.licensePlate)}
        notReadyForPickup={stage !== null && stage !== 'READY_FOR_PICKUP'}
        submitting={pendingAction === 'COMPLETE'}
        serverError={dialogError}
        onClose={() => setDialog(null)}
        onConfirm={actualCost => void run('COMPLETE', { actualCost })}
      />
    </div>
  )
}
