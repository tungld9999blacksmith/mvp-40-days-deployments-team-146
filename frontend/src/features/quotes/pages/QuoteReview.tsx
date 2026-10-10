import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useBlocker, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Car, CheckCircle2, Clock, FileX2, Phone, ShieldCheck, User, XCircle } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, CardHeader, InfoRow } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { SelectInput, TextArea } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { cn } from '@/shared/ui/cn'
import { formatDate, formatKm, formatLicensePlate, formatNumber, formatTimeDayMonth } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import ConversationExcerptPanel from '@/features/assistant/components/ConversationExcerptPanel'
import { formatVnd } from '@/features/estimate/utils'
import { approveQuote, getWorkshopQuote, rejectQuote } from '../api'
import QuoteStatusBadge from '../components/QuoteStatusBadge'
import RejectDialog from '../components/RejectDialog'
import type { QuoteItem, WorkshopQuoteDetail } from '../types'
import { hasConversation, isWaitingLong, waitingHours } from '../utils'

const MAX_PRICE = 1_000_000_000
const VALIDITY_OPTIONS = [1, 3, 5, 7, 10, 14, 21, 30]

/** Digits only; `''` keeps the estimated price (FE §4.3). */
function parsePrice(raw: string): number | null {
  const digits = raw.replace(/\D/g, '')
  return digits ? Number(digits) : null
}

function PriceInput({
  item,
  value,
  onChange,
  error,
  disabled,
}: {
  item: QuoteItem
  value: string
  onChange: (value: string) => void
  error?: string
  disabled?: boolean
}) {
  const [focused, setFocused] = useState(false)
  const parsed = parsePrice(value)
  const shown = focused || parsed === null ? value : formatNumber(parsed)
  return (
    <div>
      <input
        inputMode="numeric"
        aria-label={`Giá duyệt cho ${item.itemName}`}
        placeholder={formatNumber(item.estimatedPrice)}
        value={shown}
        disabled={disabled}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={event => onChange(event.target.value.replace(/[^\d]/g, ''))}
        className={cn(
          'w-32 bg-card border rounded-lg px-3 py-1.5 text-sm text-right font-mono text-foreground placeholder:text-muted/70 focus:outline-none focus:border-emerald/60 focus:ring-4 focus:ring-emerald/15',
          error ? 'border-error' : 'border-border',
        )}
      />
      {error && <p className="text-xs text-error mt-1 text-right">{error}</p>}
    </div>
  )
}

/** SCR-1112 / SCR-1113 — review a quote of the workshop (API-QT-12 → 14). */
export default function QuoteReview() {
  const quoteId = useSearchParams()[0].get('quoteId')
  const navigate = useNavigate()
  const toast = useToast()
  const [quote, setQuote] = useState<WorkshopQuoteDetail | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [prices, setPrices] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [validityDays, setValidityDays] = useState(7)
  const [reviewerNote, setReviewerNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [dialog, setDialog] = useState<'approve' | 'reject' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [rejectError, setRejectError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const stayRef = useRef<HTMLButtonElement>(null)
  // Read at navigation time: the review just succeeded, leaving must not be blocked.
  const doneRef = useRef(false)

  const load = useCallback(() => {
    if (!quoteId) return
    setError(null)
    getWorkshopQuote(quoteId)
      .then(data => {
        setQuote(data)
        setPrices({})
        setNotes({})
      })
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }, [quoteId])

  useEffect(load, [load])

  const pending = quote?.displayStatus === 'PENDING_APPROVAL'
  const dirty = pending && !done && (Object.values(prices).some(Boolean) || Object.values(notes).some(Boolean) || reviewerNote.trim() !== '' || validityDays !== 7)
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && !doneRef.current && currentLocation.pathname !== nextLocation.pathname,
  )

  const draftTotal = useMemo(() => {
    if (!quote) return 0
    return quote.items.reduce((sum, item) => (item.covered ? sum : sum + (parsePrice(prices[item.quoteItemId] ?? '') ?? item.estimatedPrice)), 0)
  }, [quote, prices])

  if (!quoteId) return <Navigate to="/technician/quotes" replace />

  if (error && !quote) {
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-3xl">
        <Card>
          {isApiError(error, 'QUOTE_NOT_FOUND') ? (
            <EmptyState
              icon={<FileX2 className="w-5 h-5" />}
              title="Không tìm thấy báo giá"
              action={<Button onClick={() => navigate('/technician/quotes')}>Về danh sách báo giá</Button>}
            />
          ) : (
            <ErrorState traceId={error.traceId} onRetry={load} />
          )}
        </Card>
      </div>
    )
  }

  if (!quote) {
    return (
      <div className="p-4 sm:p-6 xl:p-8 grid gap-5 lg:grid-cols-3" aria-busy>
        <div className="lg:col-span-2 space-y-4">
          <SkeletonCard lines={6} />
        </div>
        <SkeletonCard lines={4} />
      </div>
    )
  }

  const current = quote
  const changedLines = current.items.filter(item => !item.covered && parsePrice(prices[item.quoteItemId] ?? '') !== null && parsePrice(prices[item.quoteItemId] ?? '') !== item.estimatedPrice)

  function validate(): boolean {
    const errors: Record<string, string> = {}
    for (const item of current.items) {
      const price = parsePrice(prices[item.quoteItemId] ?? '')
      if (price !== null && price > MAX_PRICE) errors[item.quoteItemId] = 'Tối đa 1.000.000.000 ₫'
      if ((notes[item.quoteItemId] ?? '').length > 255) errors[`note:${item.quoteItemId}`] = 'Tối đa 255 ký tự'
    }
    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function approve() {
    setSubmitting(true)
    try {
      const items = current.items
        .filter(item => !item.covered)
        .map(item => ({ item, price: parsePrice(prices[item.quoteItemId] ?? ''), note: (notes[item.quoteItemId] ?? '').trim() }))
        .filter(({ item, price, note }) => (price !== null && price !== item.estimatedPrice) || note)
        .map(({ item, price, note }) => ({ quoteItemId: item.quoteItemId, approvedPrice: price ?? item.estimatedPrice, ...(note ? { note } : {}) }))
      const result = await approveQuote(current.quoteId, {
        validityDays,
        ...(reviewerNote.trim() ? { reviewerNote: reviewerNote.trim() } : {}),
        items,
      })
      track('quote_reviewed', { decision: 'APPROVE', modifiedLines: changedLines.length, validityDays, waitingHours: waitingHours(current) })
      doneRef.current = true
      setDone(true)
      setDialog(null)
      toast.show(`Đã duyệt báo giá — tổng ${formatVnd(result.approvedTotal ?? draftTotal)}.`, 'success')
      navigate('/technician/quotes')
    } catch (reason) {
      setDialog(null)
      if (isApiError(reason, 'QUOTE_ALREADY_REVIEWED')) {
        toast.show('Báo giá đã được xử lý.', 'info')
        load()
      } else if (isApiError(reason) && reason.code === 'COVERED_ITEM_LOCKED') {
        const lineId = reason.details?.quoteItemId
        if (typeof lineId === 'string') setFieldErrors({ [lineId]: 'Không sửa giá dòng bảo hành.' })
      } else {
        toast.show('Tạm thời chưa duyệt được, thử lại nhé.', 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function reject(reason: string) {
    setSubmitting(true)
    setRejectError(null)
    try {
      await rejectQuote(current.quoteId, reason)
      track('quote_reviewed', { decision: 'REJECT', modifiedLines: 0, validityDays: null, waitingHours: waitingHours(current) })
      doneRef.current = true
      setDone(true)
      setDialog(null)
      toast.show('Đã từ chối báo giá.', 'success')
      navigate('/technician/quotes')
    } catch (failure) {
      if (isApiError(failure, 'REVIEWER_NOTE_REQUIRED')) {
        setRejectError('Lý do từ chối cần 10–500 ký tự.')
      } else if (isApiError(failure, 'QUOTE_ALREADY_REVIEWED')) {
        setDialog(null)
        toast.show('Báo giá đã được xử lý.', 'info')
        load()
      } else {
        toast.show('Tạm thời chưa thực hiện được, thử lại nhé.', 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-6xl">
      <Link to="/technician/quotes" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground mb-3">
        <ArrowLeft className="w-4 h-4" /> Báo giá
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Duyệt báo giá</h1>
          <p className="text-muted mt-1">Mốc {formatKm(current.odoMilestone)} · {current.modelName}</p>
        </div>
        <QuoteStatusBadge status={current.displayStatus} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          {!pending && (
            <Notice tone="info" title="Báo giá đã được xử lý">
              {current.reviewedAt ? `Lúc ${formatTimeDayMonth(current.reviewedAt)}. ` : ''}Màn này chỉ để xem.
            </Notice>
          )}

          <Card className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted">
                    <th className="px-4 py-3 font-medium">Hạng mục</th>
                    <th className="px-4 py-3 font-medium text-right">Giá ước tính</th>
                    <th className="px-4 py-3 font-medium text-right">Giá duyệt</th>
                    <th className="px-4 py-3 font-medium">Ghi chú dòng</th>
                  </tr>
                </thead>
                <tbody>
                  {current.items.map(item => (
                    <tr key={item.quoteItemId} className="border-b border-border last:border-0 align-top">
                      <td className="px-4 py-3">
                        <p className="text-foreground">{item.itemName}</p>
                        {item.covered ? (
                          <Badge tone="success" icon={<ShieldCheck className="w-3 h-3" />} className="mt-1">
                            Bảo hành
                          </Badge>
                        ) : (
                          <p className="text-xs text-muted mt-0.5">{item.priceSource === 'REFERENCE_PRICE' ? 'Giá tham khảo của hãng *' : 'Giá xưởng'}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-muted whitespace-nowrap">{formatVnd(item.estimatedPrice)}</td>
                      <td className="px-4 py-3 text-right">
                        {item.covered ? (
                          <span className="font-mono text-muted">0 ₫</span>
                        ) : pending ? (
                          <PriceInput
                            item={item}
                            value={prices[item.quoteItemId] ?? ''}
                            error={fieldErrors[item.quoteItemId]}
                            disabled={submitting}
                            onChange={value => setPrices(previous => ({ ...previous, [item.quoteItemId]: value }))}
                          />
                        ) : (
                          <span className="font-mono text-foreground">{formatVnd(item.approvedPrice ?? item.estimatedPrice)}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 min-w-[160px]">
                        {item.covered ? null : pending ? (
                          <input
                            aria-label={`Ghi chú cho ${item.itemName}`}
                            maxLength={255}
                            value={notes[item.quoteItemId] ?? ''}
                            disabled={submitting}
                            onChange={event => setNotes(previous => ({ ...previous, [item.quoteItemId]: event.target.value }))}
                            placeholder="Tuỳ chọn"
                            className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-sm text-foreground placeholder:text-muted/70 focus:outline-none focus:border-emerald/60"
                          />
                        ) : (
                          <span className="text-xs text-muted">{item.reviewerNote ?? ''}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted">Tổng ước tính</p>
                <p className="font-mono text-lg text-foreground mt-0.5">{formatVnd(current.estimatedTotal)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">{pending ? 'Tổng duyệt (tạm tính)' : 'Tổng duyệt'}</p>
                <p className="font-mono text-lg font-semibold text-emerald mt-0.5">{formatVnd(pending ? draftTotal : current.approvedTotal ?? current.estimatedTotal)}</p>
              </div>
              {pending ? (
                <SelectInput label="Thời hạn hiệu lực" value={String(validityDays)} onChange={event => setValidityDays(Number(event.target.value))} disabled={submitting}>
                  {VALIDITY_OPTIONS.map(days => (
                    <option key={days} value={days}>
                      {days} ngày
                    </option>
                  ))}
                </SelectInput>
              ) : (
                current.expiresAt && (
                  <div>
                    <p className="text-xs text-muted">Hiệu lực đến</p>
                    <p className="text-lg text-foreground mt-0.5">{formatDate(current.expiresAt)}</p>
                  </div>
                )
              )}
            </div>
            {pending ? (
              <TextArea
                label="Ghi chú của chủ xưởng"
                optional
                rows={3}
                maxLength={500}
                value={reviewerNote}
                disabled={submitting}
                onChange={event => setReviewerNote(event.target.value)}
                aside={<span className="text-xs text-muted font-mono">{reviewerNote.length}/500</span>}
                helper="Khách sẽ đọc được ghi chú này."
              />
            ) : (
              current.reviewerNote && (
                <div>
                  <p className="text-xs text-muted mb-1">{current.displayStatus === 'REJECTED' ? 'Lý do từ chối' : 'Ghi chú của chủ xưởng'}</p>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{current.reviewerNote}</p>
                </div>
              )
            )}
          </Card>

          {pending && (
            <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
              <Button variant="danger" icon={<XCircle className="w-4 h-4" />} onClick={() => setDialog('reject')} disabled={submitting}>
                Từ chối
              </Button>
              <Button
                icon={<CheckCircle2 className="w-4 h-4" />}
                onClick={() => validate() && setDialog('approve')}
                disabled={submitting}
              >
                Duyệt
              </Button>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Khách hàng" icon={<User className="w-4 h-4 text-muted" />} />
            <InfoRow label="Tên" value={current.customer.fullName} />
            <InfoRow
              label="Điện thoại"
              value={
                current.customer.phone ? (
                  <a href={`tel:${current.customer.phone}`} className="inline-flex items-center gap-1 text-emerald hover:text-emerald-bright">
                    <Phone className="w-3.5 h-3.5" /> {current.customer.phone}
                  </a>
                ) : (
                  '—'
                )
              }
            />
            <InfoRow label="Xe" value={<span className="inline-flex items-center gap-1.5"><Car className="w-3.5 h-3.5 text-muted" />{current.modelName}</span>} />
            <InfoRow label="Biển số" value={formatLicensePlate(current.plateNumber)} mono />
            <InfoRow label="Gửi lúc" value={current.submittedAt ? formatTimeDayMonth(current.submittedAt) : '—'} />
            {isWaitingLong(current) && (
              <div className="pt-3">
                <Badge tone="error" icon={<Clock className="w-3.5 h-3.5" />}>
                  Chờ &gt; 24h
                </Badge>
              </div>
            )}
          </Card>
          {hasConversation(current) && <ConversationExcerptPanel source={{ type: 'quote', id: current.quoteId }} />}
        </aside>
      </div>

      <Dialog
        open={dialog === 'approve'}
        onClose={() => !submitting && setDialog(null)}
        title="Duyệt báo giá?"
        description={
          <>
            Tổng duyệt (tạm tính): <strong className="text-foreground font-mono">{formatVnd(draftTotal)}</strong>
            {changedLines.length > 0 ? ` · ${changedLines.length} dòng điều chỉnh giá` : ''} · hiệu lực {validityDays} ngày.
          </>
        }
        dismissable={!submitting}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)} disabled={submitting}>
              Xem lại
            </Button>
            <Button loading={submitting} loadingText="Đang duyệt…" onClick={() => void approve()}>
              Duyệt
            </Button>
          </>
        }
      />
      <RejectDialog
        open={dialog === 'reject'}
        onClose={() => setDialog(null)}
        onConfirm={reason => void reject(reason)}
        submitting={submitting}
        serverError={rejectError}
      />
      <Dialog
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        title="Rời trang khi chưa duyệt?"
        description="Giá và ghi chú bạn đã nhập sẽ không được lưu."
        initialFocusRef={stayRef}
        footer={
          <>
            <Button ref={stayRef} variant="secondary" onClick={() => blocker.reset?.()}>
              Ở lại
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Rời trang
            </Button>
          </>
        }
      />
    </div>
  )
}
