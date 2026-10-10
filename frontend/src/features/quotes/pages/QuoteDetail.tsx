import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarClock, CalendarPlus, FilePlus2, FileX2, Send, Store, Trash2 } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import { invalidateQuery } from '@/shared/hooks/useCachedQuery'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatDate, formatKm, formatTimeDayMonth } from '@/shared/utils/format'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { formatVnd } from '@/features/estimate/utils'
import { usePricingFlow } from '@/features/booking-lines/flow'
import { deleteQuote, getQuote, submitQuote } from '../api'
import QuoteItemTable from '../components/QuoteItemTable'
import QuoteStatusBadge from '../components/QuoteStatusBadge'
import { UNSEEN_QUOTES_KEY } from '../hooks'
import type { Quote } from '../types'

function dayMonth(iso: string): string {
  return formatDate(iso).slice(0, 5)
}

/** Total + price label by status (FE AC-FE-1101). */
function QuoteTotal({ quote }: { quote: Quote }) {
  const approved = quote.displayStatus === 'APPROVED' || quote.displayStatus === 'MODIFIED'
  const amount = quote.approvedTotal ?? quote.estimatedTotal
  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted">{approved || quote.displayStatus === 'EXPIRED' ? 'Tổng theo báo giá' : 'Tổng chi phí ước tính'}</p>
          <p className="text-3xl font-bold tracking-tight font-mono text-foreground mt-1">{formatVnd(amount)}</p>
        </div>
        {approved && quote.expiresAt ? (
          <Badge tone="success">Báo giá đã duyệt — hiệu lực đến {dayMonth(quote.expiresAt)}</Badge>
        ) : quote.displayStatus === 'EXPIRED' ? (
          <Badge tone="neutral">Đã hết hiệu lực</Badge>
        ) : (
          <Badge tone="neutral">Chi phí ước tính</Badge>
        )}
      </div>
      {!approved && quote.displayStatus !== 'EXPIRED' && (
        <p className="text-xs text-muted">Chi phí thực tế có thể thay đổi tuỳ tình trạng xe khi kiểm tra tại xưởng.</p>
      )}
    </Card>
  )
}

/** SCR-1101 / SCR-1102 — draft and detail of a quote (`/quotes/:quoteId`). */
export default function QuoteDetail() {
  const { quoteId = '' } = useParams()
  const navigate = useNavigate()
  // two_tier: quotes are history only; new bookings get their package price when booked.
  const twoTier = usePricingFlow() === 'two_tier'
  const toast = useToast()
  const [quote, setQuote] = useState<Quote | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [refreshed, setRefreshed] = useState(false)
  const [workshopInactive, setWorkshopInactive] = useState(false)
  const [dialog, setDialog] = useState<'submit' | 'delete' | null>(null)
  const [busy, setBusy] = useState(false)
  const submitKey = useRef<string | null>(null)
  const keepRef = useRef<HTMLButtonElement>(null)

  const load = useCallback(() => {
    setError(null)
    return getQuote(quoteId)
      .then(data => {
        setQuote(data)
        // Opening a reviewed quote marks the result as seen (Home badge).
        if (data.displayStatus !== 'DRAFT' && data.displayStatus !== 'PENDING_APPROVAL') invalidateQuery(UNSEEN_QUOTES_KEY)
      })
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }, [quoteId])

  useEffect(() => {
    setQuote(null)
    void load()
  }, [load])

  if (error && !quote) {
    if (isApiError(error, 'QUOTE_NOT_FOUND')) {
      return (
        <div className="p-4 sm:p-6 xl:p-8 max-w-2xl">
          <Card>
            <EmptyState
              icon={<FileX2 className="w-5 h-5" />}
              title="Không tìm thấy báo giá"
              action={<Button onClick={() => navigate('/quotes')}>Báo giá của tôi</Button>}
            />
          </Card>
        </div>
      )
    }
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-2xl">
        <Card>
          <ErrorState traceId={error.traceId} onRetry={() => void load()} />
        </Card>
      </div>
    )
  }

  if (!quote) {
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-2xl space-y-4" aria-busy>
        <SkeletonCard lines={2} />
        <SkeletonCard lines={5} />
      </div>
    )
  }

  const current = quote
  const status = current.displayStatus
  const bookingQuery = `workshopId=${encodeURIComponent(current.workshop.workshopId)}&odoMilestone=${current.odoMilestone}`

  async function submit() {
    submitKey.current ??= newId()
    setBusy(true)
    try {
      const next = await submitQuote(current.quoteId, submitKey.current)
      setQuote(next)
      setDialog(null)
      submitKey.current = null
      toast.show(`Đã gửi báo giá cho ${next.workshop.name}.`, 'success')
      track('quote_submitted', { draftAgeHours: Math.round((Date.now() - new Date(current.createdAt).getTime()) / 3_600_000) })
    } catch (reason) {
      setDialog(null)
      submitKey.current = null
      if (isApiError(reason) && reason.code === 'QUOTE_ALREADY_PENDING') {
        toast.show('Bạn đã gửi báo giá này.', 'info')
        const pending = reason.details?.pendingQuoteId
        if (typeof pending === 'string') navigate(`/quotes/${encodeURIComponent(pending)}`, { replace: true })
      } else if (isApiError(reason, 'QUOTE_DRAFT_REFRESHED')) {
        setRefreshed(true)
        void load()
      } else if (isApiError(reason, 'QUOTE_NOT_DRAFT')) {
        void load()
      } else if (isApiError(reason, 'WORKSHOP_INACTIVE')) {
        setWorkshopInactive(true)
      } else {
        toast.show('Tạm thời chưa gửi được, bạn thử lại nhé.', 'error')
      }
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    try {
      await deleteQuote(current.quoteId)
      toast.show('Đã xoá nháp.', 'success')
      navigate('/quotes', { replace: true })
    } catch (reason) {
      setDialog(null)
      if (isApiError(reason, 'QUOTE_NOT_DRAFT')) void load()
      else toast.show('Chưa xoá được nháp, bạn thử lại nhé.', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-3xl space-y-5">
      <Link to="/quotes" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Báo giá của tôi
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Store className="w-6 h-6 text-muted" /> {current.workshop.name}
          </h1>
          <p className="text-sm text-muted mt-1">Mốc {formatKm(current.odoMilestone)}</p>
        </div>
        <QuoteStatusBadge status={status} />
      </div>

      {refreshed && (
        <Notice tone="warning" title="Giá đã được cập nhật theo bảng giá mới">
          Vui lòng xem lại trước khi gửi.
        </Notice>
      )}
      {workshopInactive && (
        <Notice
          tone="error"
          title="Xưởng hiện không nhận khách"
          action={
            <Button size="sm" variant="secondary" onClick={() => navigate(`/estimate?odoMilestone=${current.odoMilestone}`)}>
              Chọn xưởng khác
            </Button>
          }
        />
      )}
      {status === 'DRAFT' && (
        <p className="text-xs text-muted">Nháp chưa gửi sẽ tự xoá sau 7 ngày{current.draftExpiresAt ? ` (${formatDate(current.draftExpiresAt)})` : ''}.</p>
      )}
      {status === 'PENDING_APPROVAL' && current.submittedAt && (
        <Notice tone="info" title="Chờ xưởng duyệt">
          Đã gửi lúc {formatTimeDayMonth(current.submittedAt)}. Bạn sẽ thấy kết quả ở đây và trên trang chủ.
        </Notice>
      )}

      <QuoteItemTable quote={current} />
      <QuoteTotal quote={current} />

      {status === 'REJECTED' && current.reviewerNote && (
        <Card className="border-error/30">
          <p className="text-[13px] font-semibold text-error mb-1.5">Lý do từ chối</p>
          <p className="text-sm text-foreground whitespace-pre-wrap">{current.reviewerNote}</p>
        </Card>
      )}
      {status !== 'REJECTED' && current.reviewerNote && (
        <Card>
          <p className="text-[13px] font-semibold text-muted mb-1.5">Ghi chú xưởng</p>
          <p className="text-sm text-foreground whitespace-pre-wrap">{current.reviewerNote}</p>
        </Card>
      )}
      {(status === 'APPROVED' || status === 'MODIFIED') && !current.canAttachToBooking && current.bookingId && (
        <Notice tone="success" title="Đã dùng cho lịch hẹn">
          <Link to={`/bookings/${encodeURIComponent(current.bookingId)}`} className="text-emerald font-medium hover:text-emerald-bright">
            Xem lịch hẹn
          </Link>
        </Notice>
      )}

      {twoTier && (status === 'DRAFT' || ((status === 'APPROVED' || status === 'MODIFIED') && current.canAttachToBooking) || status === 'EXPIRED') && (
        <Notice tone="info" title="Giá gói giờ được chốt khi đặt lịch">
          Báo giá này chỉ để tham khảo. Đặt lịch như bình thường; xưởng chỉ hỏi bạn khi có hạng mục phát sinh.
        </Notice>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        {twoTier && (status === 'DRAFT' || status === 'APPROVED' || status === 'MODIFIED' || status === 'EXPIRED') && current.bookingId === null && (
          <Button className="sm:flex-1" icon={<CalendarPlus className="w-4 h-4" />} onClick={() => navigate(`/booking?${bookingQuery}`)}>
            Đặt lịch
          </Button>
        )}
        {!twoTier && status === 'DRAFT' && (
          <>
            <Button variant="ghost" icon={<Trash2 className="w-4 h-4" />} onClick={() => setDialog('delete')}>
              Xoá nháp
            </Button>
            <Button className="sm:flex-1" icon={<Send className="w-4 h-4" />} onClick={() => setDialog('submit')} disabled={workshopInactive}>
              Gửi xưởng duyệt
            </Button>
          </>
        )}
        {!twoTier && (status === 'APPROVED' || status === 'MODIFIED') && current.canAttachToBooking && (
          <Button
            className="sm:flex-1"
            icon={<CalendarClock className="w-4 h-4" />}
            onClick={() => {
              track('quote_used_for_booking', {})
              navigate(`/booking?${bookingQuery}&quoteId=${encodeURIComponent(current.quoteId)}`)
            }}
          >
            Đặt lịch với báo giá này
          </Button>
        )}
        {!twoTier && status === 'EXPIRED' && (
          <>
            <Button variant="secondary" className="sm:flex-1" icon={<CalendarPlus className="w-4 h-4" />} onClick={() => navigate(`/booking?${bookingQuery}`)}>
              Đặt lịch không kèm báo giá
            </Button>
            <Button className="sm:flex-1" icon={<FilePlus2 className="w-4 h-4" />} onClick={() => navigate(`/estimate?odoMilestone=${current.odoMilestone}`)}>
              Lập báo giá mới
            </Button>
          </>
        )}
        {status === 'REJECTED' && (
          <Button className="sm:flex-1" icon={<FilePlus2 className="w-4 h-4" />} onClick={() => navigate(`/estimate?odoMilestone=${current.odoMilestone}`)}>
            Lập báo giá mới
          </Button>
        )}
      </div>

      <Dialog
        open={dialog === 'submit'}
        onClose={() => !busy && setDialog(null)}
        title={`Gửi báo giá cho ${current.workshop.name}?`}
        description="Xưởng sẽ xem, có thể điều chỉnh giá và duyệt hoặc từ chối. Bạn sẽ thấy kết quả tại đây."
        initialFocusRef={keepRef}
        dismissable={!busy}
        footer={
          <>
            <Button ref={keepRef} variant="secondary" onClick={() => setDialog(null)} disabled={busy}>
              Để sau
            </Button>
            <Button loading={busy} loadingText="Đang gửi…" onClick={() => void submit()}>
              Gửi xưởng duyệt
            </Button>
          </>
        }
      />
      <Dialog
        open={dialog === 'delete'}
        onClose={() => !busy && setDialog(null)}
        role="alertdialog"
        title="Xoá nháp báo giá?"
        description="Bạn có thể lập lại báo giá từ màn chi phí bảo dưỡng."
        initialFocusRef={keepRef}
        dismissable={!busy}
        footer={
          <>
            <Button ref={keepRef} variant="secondary" onClick={() => setDialog(null)} disabled={busy}>
              Giữ nháp
            </Button>
            <Button variant="danger" loading={busy} loadingText="Đang xoá…" onClick={() => void remove()}>
              Xoá nháp
            </Button>
          </>
        }
      />
    </div>
  )
}
