import { useEffect, useRef, useState } from 'react'
import { Check, Clock, ImageIcon, ShieldAlert } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { formatVnd } from '@/features/estimate/utils'
import { decideLine } from '@/features/booking-lines/api'
import {
  approveAriaLabel,
  conflictNotice,
  declineAriaLabel,
  decisionView,
  lineFromConflict,
  ownerReplyNotice,
  totalAfterApprove,
  type DecisionResult,
} from '@/features/booking-lines/logic'
import type { BookingLine, LinesView } from '@/features/booking-lines/types'

type Sheet = { line: BookingLine; kind: 'approve' | 'safety-decline' }

/** Reason of the workshop: three lines, "Xem thêm" when longer. */
function Reason({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 140
  return (
    <p className="text-sm text-muted mt-1">
      <span className={open || !long ? undefined : 'line-clamp-3'}>{text}</span>
      {long && (
        <button type="button" onClick={() => setOpen(value => !value)} className="ml-1 text-emerald text-xs font-medium hover:underline">
          {open ? 'Thu gọn' : 'Xem thêm'}
        </button>
      )}
    </p>
  )
}

function SafetyBadge() {
  return (
    <Badge tone="warning" icon={<ShieldAlert className="w-3.5 h-3.5" aria-hidden />}>
      Hạng mục an toàn
    </Badge>
  )
}

/** One line to decide (14A: stacked under `sm`, price + buttons on the right from `sm`). */
function DecisionRow({
  line,
  notice,
  busy,
  onApprove,
  onDecline,
  onPhoto,
}: {
  line: BookingLine
  notice: string | null
  busy: boolean
  onApprove: () => void
  onDecline: () => void
  onPhoto: (url: string) => void
}) {
  const photo = line.photos.find(p => p.url)
  const isPackage = line.kind === 'PACKAGE'
  return (
    <li className="py-4 first:pt-2 last:pb-1">
      {notice && (
        <Notice tone="warning" className="mb-3" role="status">
          {notice}
        </Notice>
      )}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3">
        <div className="flex gap-3 flex-1 min-w-0">
          {photo?.url ? (
            <button
              type="button"
              onClick={() => onPhoto(photo.url!)}
              className="w-14 h-14 rounded-xl overflow-hidden border border-border shrink-0 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald/25"
              aria-label={`Xem ảnh lớn: ${line.itemName}`}
            >
              <img src={photo.url} alt={`Ảnh xưởng chụp: ${line.itemName}`} className="w-full h-full object-cover" />
            </button>
          ) : line.photos.length > 0 ? (
            <span className="w-14 h-14 rounded-xl border border-border bg-card shrink-0 flex items-center justify-center text-muted" aria-label="Ảnh tạm thời chưa xem được">
              <ImageIcon className="w-5 h-5" />
            </span>
          ) : null}
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground break-words">{line.itemName}</p>
            {line.reason && <Reason text={line.reason} />}
            {line.isSafetyCritical && (
              <div className="mt-2">
                <SafetyBadge />
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:items-end shrink-0">
          <p className="font-mono text-sm text-foreground text-right whitespace-nowrap">
            {isPackage && (
              <span className="text-muted line-through mr-2" aria-label={`Giá tham khảo ${formatVnd(line.unitPrice)}`}>
                {formatVnd(line.unitPrice)}
              </span>
            )}
            {formatVnd(line.price)}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <Button
              variant="secondary"
              className="h-11 sm:h-auto"
              icon={<Check className="w-4 h-4 text-emerald" />}
              aria-label={approveAriaLabel(line)}
              disabled={busy}
              onClick={onApprove}
            >
              Đồng ý
            </Button>
            <Button variant="secondary" className="h-11 sm:h-auto" aria-label={declineAriaLabel(line)} disabled={busy} onClick={onDecline}>
              {isPackage ? 'Không làm hạng mục này' : 'Không làm'}
            </Button>
          </div>
        </div>
      </div>
      {isPackage && <p className="text-xs text-muted mt-2">Nếu không đồng ý, xưởng sẽ không làm hạng mục này trong lần bảo dưỡng này.</p>}
    </li>
  )
}

/**
 * Design 1A / 16A / OV4 — "Cần bạn quyết định" on the owner's ticket: the only
 * place where a line is approved or declined. Price increases of package items
 * first, then extras; after the last decision a summary stays until the next load.
 */
export default function DecisionCard({
  view,
  onChange,
  onReload,
  announce,
  onBusyChange,
}: {
  view: LinesView
  onChange: (next: LinesView) => void
  /** Fetch the lines again (after a conflict); resolves to the fresh view. */
  onReload: () => Promise<LinesView | null>
  /** Page-level aria-live region (always mounted). */
  announce: (message: string) => void
  onBusyChange?: (busy: boolean) => void
}) {
  const toast = useToast()
  const [decided, setDecided] = useState<Record<string, DecisionResult>>({})
  const [sheet, setSheet] = useState<Sheet | null>(null)
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [notices, setNotices] = useState<Record<string, string>>({})
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const summaryTitle = useRef<HTMLHeadingElement>(null)
  const shown = decisionView(view, decided)
  const replyNotice = ownerReplyNotice(view.lines)

  useEffect(() => {
    onBusyChange?.(sheet !== null || submitting !== null)
  }, [sheet, submitting, onBusyChange])

  useEffect(() => {
    if (shown.mode === 'summary') summaryTitle.current?.focus()
  }, [shown.mode])

  if (shown.mode === 'hidden') return null

  async function decide(line: BookingLine, decision: 'APPROVE' | 'DECLINE', confirmSafety = false) {
    if (submitting) return
    setSubmitting(line.lineId)
    try {
      const next = await decideLine(view.bookingId, line.lineId, { decision, seenVersion: line.version, confirmSafety })
      const result: DecisionResult = decision === 'APPROVE' ? 'APPROVED' : 'DECLINED'
      setDecided(current => ({ ...current, [line.lineId]: result }))
      setNotices(current => {
        const rest = { ...current }
        delete rest[line.lineId]
        return rest
      })
      setSheet(null)
      onChange(next)
      announce(`${decision === 'APPROVE' ? 'Đã đồng ý' : 'Đã chọn không làm'} ${line.itemName}.`)
      track('booking_line_decided', { decision, kind: line.kind, safety: line.isSafetyCritical })
    } catch (failure) {
      setSheet(null)
      if (isApiError(failure) && failure.code === 'LINE_CHANGED') {
        const fresh = await onReload()
        const after = fresh?.lines.find(item => item.lineId === line.lineId) ?? lineFromConflict(line, failure.details)
        const message = conflictNotice(line, after)
        setNotices(current => ({ ...current, [line.lineId]: message }))
        announce(message)
      } else if (isApiError(failure, 'SAFETY_CONFIRMATION_REQUIRED')) {
        setSheet({ line, kind: 'safety-decline' })
      } else {
        toast.show('Chưa gửi được quyết định, bạn thử lại nhé.', 'error')
      }
    } finally {
      setSubmitting(null)
    }
  }

  const rows = (lines: BookingLine[]) => (
    <ul className="divide-y divide-border">
      {lines.map(line => (
        <DecisionRow
          key={line.lineId}
          line={line}
          notice={notices[line.lineId] ?? null}
          busy={submitting !== null}
          onApprove={() => setSheet({ line, kind: 'approve' })}
          onDecline={() => (line.isSafetyCritical ? setSheet({ line, kind: 'safety-decline' }) : void decide(line, 'DECLINE'))}
          onPhoto={setPhotoUrl}
        />
      ))}
    </ul>
  )

  return (
    <Card>
      {shown.mode === 'pending' ? (
        <>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-foreground">Cần bạn quyết định</h2>
            <Badge tone="warning">{shown.packageChanges.length + shown.extras.length} hạng mục</Badge>
          </div>
          <p className="text-sm text-muted mt-1">Xưởng chỉ làm các hạng mục bạn đồng ý. Hạng mục bạn không chọn sẽ không tính tiền.</p>
          {replyNotice && (
            <p className="flex items-center gap-1.5 text-sm text-warning mt-2">
              <Clock className="w-4 h-4 shrink-0" aria-hidden />
              {replyNotice}
            </p>
          )}
          {shown.packageChanges.length > 0 && (
            <section aria-label="Giá gói thay đổi" className="mt-4">
              <p className="text-[13px] font-semibold text-muted">Giá gói thay đổi</p>
              {rows(shown.packageChanges)}
            </section>
          )}
          {shown.extras.length > 0 && (
            <section aria-label="Hạng mục phát sinh" className="mt-4">
              <p className="text-[13px] font-semibold text-muted">Hạng mục phát sinh</p>
              {rows(shown.extras)}
            </section>
          )}
          <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-sm">
            <span className="text-muted">Tổng hiện tại → nếu đồng ý hết</span>
            <span className="font-mono text-foreground">
              {formatVnd(view.currentTotal)} → {formatVnd(view.totalIfAllApproved)}
            </span>
          </div>
        </>
      ) : (
        <>
          <h2 ref={summaryTitle} tabIndex={-1} className="text-base font-semibold text-foreground focus:outline-none">
            Bạn đã gửi quyết định cho xưởng
          </h2>
          <ul className="divide-y divide-border mt-2">
            {shown.decided.map(item => (
              <li key={item.lineId} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="text-foreground">{item.itemName}</span>
                <span className="whitespace-nowrap">
                  <span className={item.result === 'APPROVED' ? 'text-emerald' : 'text-muted'}>{item.result === 'APPROVED' ? 'Đồng ý' : 'Không làm'}</span>
                  <span className="font-mono text-foreground ml-2">{formatVnd(item.price)}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <Dialog
        open={sheet?.kind === 'approve'}
        onClose={() => !submitting && setSheet(null)}
        dismissable={!submitting}
        title={sheet ? `Thêm ${sheet.line.itemName} · ${formatVnd(sheet.line.price)}?` : ''}
        description={sheet ? `Tổng mới ${formatVnd(totalAfterApprove(view, sheet.line))}` : undefined}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)} disabled={Boolean(submitting)}>
              Huỷ
            </Button>
            <Button loading={Boolean(submitting)} loadingText="Đang gửi…" onClick={() => sheet && void decide(sheet.line, 'APPROVE')}>
              Xác nhận
            </Button>
          </>
        }
      />
      <Dialog
        open={sheet?.kind === 'safety-decline'}
        role="alertdialog"
        onClose={() => !submitting && setSheet(null)}
        dismissable={!submitting}
        title={sheet ? `Không làm ${sheet.line.itemName}?` : ''}
        description="Đây là hạng mục an toàn (phanh, lốp, lái hoặc đèn). Bỏ qua có thể ảnh hưởng an toàn khi lái xe. Quyết định vẫn là của bạn."
        footer={
          <>
            <Button variant="secondary" onClick={() => setSheet(null)} disabled={Boolean(submitting)}>
              Xem lại
            </Button>
            <Button variant="danger" loading={Boolean(submitting)} loadingText="Đang gửi…" onClick={() => sheet && void decide(sheet.line, 'DECLINE', true)}>
              Vẫn không làm
            </Button>
          </>
        }
      />
      <Dialog open={photoUrl !== null} onClose={() => setPhotoUrl(null)} title="Ảnh xưởng chụp" className="sm:max-w-lg">
        {photoUrl && <img src={photoUrl} alt="Ảnh xưởng chụp" className="w-full rounded-xl" />}
      </Dialog>
    </Card>
  )
}
