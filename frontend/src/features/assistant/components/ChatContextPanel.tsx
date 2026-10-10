import { BatteryCharging, CalendarClock, CircleDot, ShieldCheck, Wrench, type LucideIcon } from 'lucide-react'
import PlateTile from '@/shared/ui/PlateTile'
import Spinner from '@/shared/ui/Spinner'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { formatKm, formatNumber, formatTimeDayMonth } from '@/shared/utils/format'
import DueStatusBadge from '@/features/vehicles/components/DueStatusBadge'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import { remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import type { VehicleSummary } from '@/features/vehicles/types'
import { QUICK_BOOKING_LABEL } from '../quickBooking/proposalView'

export const SUGGESTED_QUESTIONS = [
  'Mốc bảo dưỡng tới của xe tôi cần làm gì?',
  'Hạng mục nào được bảo hành miễn phí?',
  'Chính sách bảo hành pin thế nào?',
  'Bao lâu cần kiểm tra lốp?',
]

const QUESTION_ICONS: LucideIcon[] = [Wrench, ShieldCheck, BatteryCharging, CircleDot]

function Readout({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-2xl bg-card px-3.5 py-3">
      <p className="font-plate font-bold text-[32px] leading-none text-foreground">{value}</p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  )
}

/**
 * Vehicle context shown next to the chat (US-025 FE §4.5). Display only — nothing
 * from here is sent with the message (the backend loads the vehicle, AC-603).
 */
export default function ChatContextPanel({
  vehicle,
  onAsk,
  onQuickBooking,
  disabled,
  showSuggestions = true,
}: {
  vehicle: VehicleSummary | null
  onAsk: (question: string) => void
  /** us-061 — the quick-booking chip; never sent as a chat question. */
  onQuickBooking: () => void
  disabled?: boolean
  /** Off while the chat's empty state already shows the same questions. */
  showSuggestions?: boolean
}) {
  const status = useMaintenanceStatus(vehicle?.userVehicleId ?? null)
  const data = status.data
  const parts = data && data.dueStatus !== 'UNKNOWN' ? remainingParts(data) : []

  // Big readouts only while counting down; overdue and unknown states keep the sentence form.
  const countdown = data && data.dueStatus !== 'UNKNOWN' && (data.remainingKm ?? 0) > 0 && (data.remainingDays ?? 0) > 0

  return (
    <div className="p-5 space-y-6">
      <section>
        <p className="text-[13px] font-semibold text-muted mb-3">Xe đang hỏi</p>
        <div className="bg-background rounded-[20px] p-4 space-y-4">
          {vehicle ? (
            <>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-base font-extrabold tracking-tight text-foreground">{vehicleDisplayName(vehicle.modelName, vehicle.trim)}</p>
                  {data?.odometer && (
                    <p className="text-xs text-muted mt-0.5">
                      ODO <span className="font-mono text-foreground">{formatKm(data.odometer.odoKm)}</span>
                    </p>
                  )}
                </div>
                {vehicle.licensePlate && <PlateTile plate={vehicle.licensePlate} size="sm" className="flex-shrink-0" />}
              </div>
              {data ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <DueStatusBadge status={data.dueStatus} />
                    {data.nextMilestone && (
                      <span className="text-xs text-muted">
                        Mốc <span className="font-mono text-foreground">{formatKm(data.nextMilestone.odoMilestoneKm)}</span>
                      </span>
                    )}
                  </div>
                  {data.unknownReason === 'OEM_DATA_NOT_SYNCED' ? (
                    <p className="text-xs text-muted">Đang lấy dữ liệu từ hãng...</p>
                  ) : countdown ? (
                    <div className="grid grid-cols-2 gap-2">
                      <Readout value={formatNumber(data.remainingKm ?? 0)} label="km còn lại" />
                      <Readout value={formatNumber(data.remainingDays ?? 0)} label="ngày còn lại" />
                    </div>
                  ) : (
                    parts.length > 0 && <p className="text-sm font-mono text-foreground">{parts.map(part => part.text).join(' · ')}</p>
                  )}
                  {data.odometer && (
                    <p className="text-xs text-muted">
                      Hãng cập nhật <span className="font-mono">{formatTimeDayMonth(data.odometer.recordedAt)}</span>
                    </p>
                  )}
                </div>
              ) : (
                status.isFetching && <Spinner className="w-4 h-4 text-muted" label="Đang tải" />
              )}
            </>
          ) : (
            <p className="text-sm text-muted">Chưa có xe được liên kết.</p>
          )}
        </div>
      </section>

      {showSuggestions && (
        <section>
          <p className="text-[13px] font-semibold text-muted mb-3">Hỏi nhanh</p>
          <div className="space-y-2">
            <button
              type="button"
              disabled={disabled || !vehicle}
              onClick={onQuickBooking}
              className="w-full min-h-12 text-left rounded-2xl bg-brand text-on-brand px-3 py-2.5 text-[13px] font-semibold hover:bg-emerald-bright transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3"
            >
              <span className="w-8 h-8 rounded-[10px] bg-card text-emerald flex items-center justify-center flex-shrink-0">
                <CalendarClock className="w-4 h-4" aria-hidden />
              </span>
              {QUICK_BOOKING_LABEL}
            </button>
            {!vehicle && <p className="text-xs text-muted">Liên kết xe để đặt lịch.</p>}
            {SUGGESTED_QUESTIONS.map((question, index) => {
              const Icon = QUESTION_ICONS[index] ?? Wrench
              return (
                <button
                  key={question}
                  type="button"
                  disabled={disabled}
                  onClick={() => onAsk(question)}
                  className="w-full min-h-12 text-left rounded-2xl bg-background px-3 py-2.5 text-[13px] font-medium text-foreground hover:bg-card-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3"
                >
                  <span className="w-8 h-8 rounded-[10px] bg-card text-emerald flex items-center justify-center flex-shrink-0">
                    <Icon className="w-4 h-4" aria-hidden />
                  </span>
                  {question}
                </button>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
