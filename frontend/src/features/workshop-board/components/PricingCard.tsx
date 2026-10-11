import { useCallback, useEffect, useState } from 'react'
import { Phone, PhoneCall, Plus, ReceiptText, ShieldAlert, ShieldCheck } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, CardHeader } from '@/shared/ui/Card'
import { TextArea } from '@/shared/ui/Field'
import MoneyInput from '@/shared/ui/MoneyInput'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatVnd } from '@/features/estimate/utils'
import { confirmPackageLine, editLine, getWorkshopBookingLines, recordPhoneDecision, withdrawLine } from '@/features/booking-lines/api'
import {
  REASON_MAX,
  WORKSHOP_LINE_STATUS,
  confirmButtonLabel,
  parsePrice,
  reasonError,
  reasonRequired,
  replyState,
  workshopLinesView,
  workshopReplyText,
} from '@/features/booking-lines/logic'
import type { BookingLine, LinesView } from '@/features/booking-lines/types'
import ExtraItemDrawer from './ExtraItemDrawer'
import PhoneDecisionDialog from './PhoneDecisionDialog'

const ERROR_TEXT: Record<string, string> = {
  LINE_CHANGED: 'Dòng này vừa thay đổi (chủ xe đã quyết định hoặc có người sửa). Đã tải lại.',
  BOOKING_STATUS_INVALID: 'Lịch hẹn đã chuyển trạng thái. Đã tải lại.',
  REASON_REQUIRED: 'Lý do cần 10–500 ký tự.',
  SAFETY_CONFIRMATION_REQUIRED: 'Hạng mục an toàn: đánh dấu đã nói rõ với chủ xe trước khi lưu "Không làm".',
}

type Draft = { price: string; reason: string }

/**
 * One row whose price the workshop sets: confirming a reference price after
 * check-in (17A), or editing a line still waiting for the owner. Typed values
 * live in the parent, so a background refresh never wipes them (OV3).
 */
function PriceEditor({
  line,
  reference,
  draft,
  busy,
  submitLabel,
  onDraft,
  onSubmit,
  onCancel,
}: {
  line: BookingLine
  reference: number
  draft: Draft
  busy: boolean
  submitLabel?: string
  onDraft: (draft: Draft) => void
  onSubmit: (price: number, reason: string) => void
  onCancel?: () => void
}) {
  const price = parsePrice(draft.price)
  const needsReason = line.kind === 'EXTRA' || reasonRequired(price, reference)
  const error = reasonError(draft.reason, needsReason)
  const blocked = price === null || error !== null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <MoneyInput
          value={draft.price}
          onChange={value => onDraft({ ...draft, price: value })}
          ariaLabel={`Giá xác nhận cho ${line.itemName}`}
          placeholder={reference}
          disabled={busy}
        />
        <div className="flex gap-2">
          {onCancel && (
            <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
              Huỷ
            </Button>
          )}
          <Button size="sm" variant="secondary" loading={busy} disabled={blocked} onClick={() => price !== null && onSubmit(price, draft.reason.trim())}>
            {submitLabel ?? confirmButtonLabel(price, reference)}
          </Button>
        </div>
      </div>
      {needsReason && (
        <TextArea
          label={line.kind === 'EXTRA' ? 'Lý do (chủ xe sẽ thấy)' : 'Lý do tăng giá (chủ xe sẽ thấy)'}
          rows={3}
          maxLength={REASON_MAX}
          value={draft.reason}
          onChange={event => onDraft({ ...draft, reason: event.target.value })}
          error={draft.reason && error ? error : undefined}
          helper={!draft.reason ? 'Lý do cần ít nhất 10 ký tự' : undefined}
          disabled={busy}
          aside={
            <span className="text-xs text-muted font-mono" aria-hidden>
              {draft.reason.trim().length}/{REASON_MAX}
            </span>
          }
        />
      )}
    </div>
  )
}

/** Design 2A / 4A / 9B — "Giá & phát sinh" on the board detail of a two-tier booking. */
export default function PricingCard({
  bookingId,
  bookingStatus,
  readOnly,
  refreshKey,
  onChanged,
  customerPhone,
}: {
  bookingId: string
  bookingStatus: string
  readOnly: boolean
  /** Called when the owner has not answered a line within 10 minutes. */
  customerPhone?: string
  /** Bumped by the board's 15 s refresh. */
  refreshKey: number
  /** Lines changed: the board reloads the detail (blocked actions, totals). */
  onChanged: () => void
}) {
  const toast = useToast()
  const [view, setView] = useState<LinesView | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [phoneLine, setPhoneLine] = useState<BookingLine | null>(null)

  const load = useCallback(
    () =>
      getWorkshopBookingLines(bookingId)
        .then(data => {
          setView(data)
          setError(null)
        })
        .catch((reason: unknown) => setError(isApiError(reason) ? reason : null)),
    [bookingId],
  )

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  if (!view) {
    if (error) return <ErrorState title="Không tải được giá & phát sinh." traceId={error.traceId} onRetry={() => void load()} />
    return <SkeletonCard lines={3} />
  }
  if (view.pricingFlow !== 'two_tier') return null

  const split = workshopLinesView(view)
  const draftOf = (line: BookingLine): Draft => drafts[line.lineId] ?? { price: String(line.price), reason: '' }
  const setDraft = (lineId: string, draft: Draft) => setDrafts(current => ({ ...current, [lineId]: draft }))
  const clearDraft = (lineId: string) =>
    setDrafts(current => {
      const rest = { ...current }
      delete rest[lineId]
      return rest
    })

  async function run(lineId: string, action: () => Promise<LinesView>, success: string) {
    setBusy(lineId)
    try {
      setView(await action())
      clearDraft(lineId)
      setEditing(null)
      setPhoneLine(null)
      toast.show(success, 'success')
      onChanged()
    } catch (failure) {
      const code = isApiError(failure) ? failure.code : ''
      toast.show(ERROR_TEXT[code] ?? (isApiError(failure) ? failure.message : 'Chưa lưu được, bạn thử lại nhé.'), 'warning')
      if (code === 'LINE_CHANGED' || code === 'BOOKING_STATUS_INVALID') {
        setPhoneLine(null)
        void load()
        onChanged()
      }
    } finally {
      setBusy(null)
    }
  }

  const canConfirm = !readOnly && bookingStatus === 'CHECKED_IN'
  const canEdit = !readOnly && (bookingStatus === 'CHECKED_IN' || bookingStatus === 'IN_PROGRESS')
  const canPropose = !readOnly && bookingStatus === 'IN_PROGRESS'

  return (
    <Card>
      <CardHeader
        title="Giá & phát sinh"
        icon={<ReceiptText className="w-4 h-4 text-muted" />}
        action={<span className="font-mono text-sm text-foreground">{formatVnd(view.currentTotal)}</span>}
      />

      {view.packageNotice && split.unconfirmed.length + split.settledPackage.length === 0 && (
        <p className="text-sm text-muted mb-3">Không có gói chuẩn cho mốc này: mọi hạng mục là phát sinh chủ xe duyệt.</p>
      )}

      {split.unconfirmed.length > 0 && (
        <section aria-label="Xác nhận giá gói" className="mb-4">
          <p className="text-[13px] font-semibold text-muted">Xác nhận giá gói</p>
          {!canConfirm && <p className="text-xs text-muted mt-1">Xác nhận giá sau khi nhận xe.</p>}
          <ul className="divide-y divide-border">
            {split.unconfirmed.map(line => (
              <li key={line.lineId} className="py-3 space-y-2">
                <div className="flex items-start justify-between gap-3 text-sm">
                  <span className="text-foreground">{line.itemName}</span>
                  <span className="text-xs text-muted whitespace-nowrap">Tham khảo {formatVnd(line.unitPrice)}</span>
                </div>
                {canConfirm && (
                  <PriceEditor
                    line={line}
                    reference={line.unitPrice}
                    draft={draftOf(line)}
                    busy={busy === line.lineId}
                    onDraft={draft => setDraft(line.lineId, draft)}
                    onSubmit={(price, reason) =>
                      void run(
                        line.lineId,
                        () => confirmPackageLine(bookingId, line.lineId, { expectedVersion: line.version, price, ...(reason ? { reason } : {}) }),
                        price > line.unitPrice ? 'Đã gửi chủ xe duyệt giá mới.' : 'Đã xác nhận giá.',
                      )
                    }
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {split.settledPackage.length > 0 && (
        <section aria-label="Gói đã chốt" className="mb-4">
          <p className="text-[13px] font-semibold text-muted">Gói bảo dưỡng</p>
          <ul className="divide-y divide-border">
            {split.settledPackage.map(line => (
              <li key={line.lineId} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className={line.status === 'DECLINED' ? 'text-muted line-through' : 'text-foreground'}>{line.itemName}</span>
                <span className="flex items-center gap-2 whitespace-nowrap">
                  {line.status === 'DECLINED' && <Badge tone="neutral">Không làm</Badge>}
                  {line.isCoveredByWarranty ? (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald">
                      <ShieldCheck className="w-3.5 h-3.5" aria-hidden /> Bảo hành
                    </span>
                  ) : (
                    <span className="font-mono text-foreground">{formatVnd(line.price)}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Phát sinh">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[13px] font-semibold text-muted">Phát sinh</p>
          {canPropose && (
            <Button size="sm" variant="secondary" icon={<Plus className="w-4 h-4" />} onClick={() => setDrawer(true)}>
              Thêm phát sinh
            </Button>
          )}
        </div>
        {split.extras.length === 0 ? (
          <p className="text-sm text-muted mt-2">Chưa có hạng mục phát sinh. Phát hiện thêm việc cần làm khi kiểm tra xe thì thêm ở đây.</p>
        ) : (
          <ul className="divide-y divide-border">
            {split.extras.map(line => {
              const status = WORKSHOP_LINE_STATUS[line.status]
              const waiting = line.status === 'PROPOSED'
              const reply = replyState(line)
              const replyText = canEdit ? workshopReplyText(reply) : null
              // Not done, not charged: struck like on the owner's ticket (QA ISSUE-005).
              const dropped = line.status === 'DECLINED' || line.status === 'WITHDRAWN'
              return (
                <li key={line.lineId} className="py-3 space-y-2">
                  <div className="flex items-start justify-between gap-3 text-sm">
                    <span className="min-w-0">
                      <span className={dropped ? 'text-muted line-through break-words' : 'text-foreground break-words'}>{line.itemName}</span>
                      <span className="flex flex-wrap items-center gap-2 mt-1">
                        <Badge tone={status.tone}>{status.label}</Badge>
                        {line.kind === 'PACKAGE' && <span className="text-xs text-muted">Tăng giá gói</span>}
                        {line.isSafetyCritical && <ShieldAlert className="w-3.5 h-3.5 text-warning" aria-label="Hạng mục an toàn" />}
                        {line.photos.length > 0 && <span className="text-xs text-muted">{line.photos.length} ảnh</span>}
                        {line.decidedVia === 'PHONE' && (
                          <span className="inline-flex items-center gap-1 text-xs text-muted">
                            <Phone className="w-3.5 h-3.5" aria-hidden /> Qua điện thoại · {line.phoneConfirmedBy}
                          </span>
                        )}
                        {waiting && line.disputedAt && <span className="text-xs text-warning">Chủ xe không đồng ý ghi nhận qua điện thoại</span>}
                      </span>
                      {replyText &&
                        (reply.kind === 'call' ? (
                          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs font-medium text-warning">
                            <PhoneCall className="w-3.5 h-3.5" aria-hidden />
                            {replyText}
                            {customerPhone && (
                              <a href={`tel:${customerPhone}`} className="font-mono underline underline-offset-2">
                                {customerPhone}
                              </a>
                            )}
                          </span>
                        ) : (
                          <span className="block mt-1 text-xs text-muted">{replyText}</span>
                        ))}
                    </span>
                    <span className={`font-mono whitespace-nowrap ${dropped ? 'text-muted line-through' : 'text-foreground'}`}>{formatVnd(line.price)}</span>
                  </div>
                  {waiting && canEdit && editing !== line.lineId && (
                    <div className="flex gap-2">
                      <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => setEditing(line.lineId)}>
                        Sửa
                      </Button>
                      <Button size="sm" variant="ghost" icon={<Phone className="w-4 h-4" />} disabled={busy !== null} onClick={() => setPhoneLine(line)}>
                        Ghi qua điện thoại
                      </Button>
                      {line.kind === 'EXTRA' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={busy === line.lineId}
                          disabled={busy !== null}
                          onClick={() => void run(line.lineId, () => withdrawLine(bookingId, line.lineId, line.version), 'Đã rút hạng mục.')}
                        >
                          Rút
                        </Button>
                      )}
                    </div>
                  )}
                  {waiting && editing === line.lineId && (
                    <PriceEditor
                      line={line}
                      reference={line.kind === 'PACKAGE' ? line.unitPrice : Number.POSITIVE_INFINITY}
                      draft={drafts[line.lineId] ?? { price: String(line.price), reason: line.reason ?? '' }}
                      busy={busy === line.lineId}
                      submitLabel="Gửi lại chủ xe"
                      onDraft={draft => setDraft(line.lineId, draft)}
                      onCancel={() => {
                        clearDraft(line.lineId)
                        setEditing(null)
                      }}
                      onSubmit={(price, reason) =>
                        void run(
                          line.lineId,
                          () => editLine(bookingId, line.lineId, { expectedVersion: line.version, price, ...(reason ? { reason } : {}) }),
                          'Đã gửi lại chủ xe.',
                        )
                      }
                    />
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <PhoneDecisionDialog
        line={phoneLine}
        busy={phoneLine !== null && busy === phoneLine.lineId}
        onClose={() => setPhoneLine(null)}
        onSubmit={body =>
          phoneLine &&
          void run(
            phoneLine.lineId,
            () => recordPhoneDecision(bookingId, phoneLine.lineId, { ...body, seenVersion: phoneLine.version }),
            'Đã lưu và báo chủ xe.',
          )
        }
      />
      <ExtraItemDrawer
        open={drawer}
        bookingId={bookingId}
        onClose={() => setDrawer(false)}
        onSent={next => {
          setView(next)
          setDrawer(false)
          toast.show('Đã gửi chủ xe duyệt.', 'success')
          onChanged()
        }}
      />
    </Card>
  )
}
