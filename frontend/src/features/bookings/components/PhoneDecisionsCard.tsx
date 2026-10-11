import { useState } from 'react'
import { Phone } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { formatVnd } from '@/features/estimate/utils'
import { disputeLine } from '@/features/booking-lines/api'
import { phoneDisputable } from '@/features/booking-lines/logic'
import type { BookingLine, LinesView } from '@/features/booking-lines/types'

/**
 * TODOS P2 (concern R2-2) — decisions the workshop recorded by phone. Until the car is
 * completed the owner can say "Tôi không đồng ý": the line goes back to "Cần bạn quyết
 * định", is not charged, and the workshop cannot complete before the owner decides.
 */
export default function PhoneDecisionsCard({
  view,
  onChange,
  onReload,
  announce,
}: {
  view: LinesView
  onChange: (next: LinesView) => void
  onReload: () => Promise<LinesView | null>
  announce: (message: string) => void
}) {
  const toast = useToast()
  const [sheet, setSheet] = useState<BookingLine | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const lines = phoneDisputable(view)
  if (lines.length === 0) return null

  async function dispute(line: BookingLine) {
    setSubmitting(true)
    try {
      onChange(await disputeLine(view.bookingId, line.lineId, line.version))
      announce(`${line.itemName} quay lại chờ bạn quyết định.`)
      track('booking_line_disputed', { kind: line.kind, decision: line.status })
    } catch (failure) {
      if (isApiError(failure) && failure.code === 'LINE_CHANGED') {
        await onReload()
        toast.show('Hạng mục vừa thay đổi, bạn xem lại nhé.', 'warning')
      } else if (isApiError(failure, 'BOOKING_STATUS_INVALID')) {
        await onReload()
        toast.show('Xe đã hoàn tất, không đổi được nữa. Liên hệ xưởng nếu cần.', 'warning')
      } else {
        toast.show('Chưa gửi được, bạn thử lại nhé.', 'error')
      }
    } finally {
      setSubmitting(false)
      setSheet(null)
    }
  }

  return (
    <Card>
      <h2 className="text-base font-semibold text-foreground">Xưởng ghi nhận qua điện thoại</h2>
      <p className="text-sm text-muted mt-1">Nếu không đúng ý bạn, bấm "Tôi không đồng ý" trước khi xe hoàn tất.</p>
      <ul className="divide-y divide-border mt-2">
        {lines.map(line => (
          <li key={line.lineId} className="py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground break-words">{line.itemName}</p>
              <p className="text-xs text-muted mt-0.5 inline-flex items-center gap-1">
                <Phone className="w-3.5 h-3.5" aria-hidden />
                {line.phoneConfirmedBy}
              </p>
            </div>
            <span className="text-sm whitespace-nowrap">
              <span className={line.status === 'APPROVED' ? 'text-emerald' : 'text-muted'}>{line.status === 'APPROVED' ? 'Đồng ý' : 'Không làm'}</span>
              <span className="font-mono text-foreground ml-2">{formatVnd(line.price)}</span>
            </span>
            <Button variant="secondary" size="sm" disabled={submitting} onClick={() => setSheet(line)} aria-label={`Tôi không đồng ý: ${line.itemName}`}>
              Tôi không đồng ý
            </Button>
          </li>
        ))}
      </ul>
      <Dialog
        open={sheet !== null}
        onClose={() => !submitting && setSheet(null)}
        dismissable={!submitting}
        title={sheet ? `Không đồng ý với ghi nhận ${sheet.itemName}?` : ''}
        description="Hạng mục quay lại mục Cần bạn quyết định và chưa tính tiền. Xưởng chỉ hoàn tất sau khi bạn chọn lại."
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)} disabled={submitting}>
              Huỷ
            </Button>
            <Button loading={submitting} loadingText="Đang gửi…" onClick={() => sheet && void dispute(sheet)}>
              Tôi không đồng ý
            </Button>
          </>
        }
      />
    </Card>
  )
}
