import { CalendarClock, Car } from 'lucide-react'
import Spinner from '@/shared/ui/Spinner'
import { vehicleDisplayName } from '@/shared/domain/labels'
import { formatKm, formatLicensePlate, formatTimeDayMonth } from '@/shared/utils/format'
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

  return (
    <div className="p-5 space-y-6">
      <section>
        <p className="text-[13px] font-semibold text-muted mb-3">Thông tin xe</p>
        <div className="bg-card border border-border rounded-2xl p-4 space-y-3 elevation-sm">
          {vehicle ? (
            <>
              <div className="flex items-center gap-2.5">
                <Car className="w-4 h-4 text-emerald" aria-hidden />
                <span className="text-sm font-semibold text-foreground">{vehicleDisplayName(vehicle.modelName, vehicle.trim)}</span>
              </div>
              <p className="text-xs font-mono text-muted">{formatLicensePlate(vehicle.licensePlate)}</p>
              {data ? (
                <div className="space-y-2 pt-1">
                  <DueStatusBadge status={data.dueStatus} />
                  {data.unknownReason === 'OEM_DATA_NOT_SYNCED' ? (
                    <p className="text-xs text-muted">Đang lấy dữ liệu từ hãng...</p>
                  ) : (
                    parts.length > 0 && <p className="text-sm font-mono text-foreground">{parts.map(part => part.text).join(' · ')}</p>
                  )}
                  {data.odometer && (
                    <p className="text-xs text-muted">
                      ODO <span className="font-mono text-foreground">{formatKm(data.odometer.odoKm)}</span> · Hãng cập nhật{' '}
                      <span className="font-mono">{formatTimeDayMonth(data.odometer.recordedAt)}</span>
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
          <p className="text-[13px] font-semibold text-muted mb-3">Câu hỏi gợi ý</p>
          <div className="space-y-2">
            <button
              type="button"
              disabled={disabled || !vehicle}
              onClick={onQuickBooking}
              className="w-full text-left rounded-xl border border-border bg-card px-3.5 py-2.5 text-sm text-foreground hover:bg-card-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <CalendarClock className="w-3.5 h-3.5 text-emerald flex-shrink-0" aria-hidden />
              {QUICK_BOOKING_LABEL}
            </button>
            {!vehicle && <p className="text-xs text-muted">Liên kết xe để đặt lịch.</p>}
            {SUGGESTED_QUESTIONS.map(question => (
              <button
                key={question}
                type="button"
                disabled={disabled}
                onClick={() => onAsk(question)}
                className="w-full text-left rounded-xl border border-border bg-card px-3.5 py-2.5 text-sm text-foreground hover:bg-card-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {question}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
