import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarCheck2, Clock, Heart, MessageSquareWarning, Phone, ShieldAlert } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { TextArea } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatDate } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { getFollowUp, respondFollowUp } from '../api'
import StarRating, { RATING_LABELS } from '../components/StarRating'
import type { FollowUp as FollowUpData, FollowUpOutcome } from '../types'

const MAX_COMMENT = 1000

function CallButton({ hotline, label = 'Gọi xưởng' }: { hotline: string; label?: string }) {
  return (
    <a
      href={`tel:${hotline.replace(/\s+/g, '')}`}
      className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold bg-warning text-on-brand hover:brightness-110 transition"
    >
      <Phone className="w-4 h-4" /> {label}
    </a>
  )
}

/** §4.4 — texts come from the API (`message`, `safetyMessage`), the FE never writes its own (BR-912). */
function ResultPanel({ outcome, workshop }: { outcome: FollowUpOutcome; workshop: FollowUpData['workshop'] }) {
  const navigate = useNavigate()
  return (
    <div className="space-y-4">
      {outcome.safetyAdvice && (
        <div role="alert" className="rounded-2xl border border-warning/30 bg-warning/10 p-4 space-y-3">
          <p className="flex items-start gap-2 text-sm text-foreground">
            <ShieldAlert className="w-5 h-5 text-warning shrink-0" />
            <span>{outcome.safetyMessage ?? `Nếu xe có dấu hiệu bất thường khi vận hành, bạn nên dừng xe và liên hệ xưởng ngay: ${workshop.hotline}.`}</span>
          </p>
          <CallButton hotline={workshop.hotline} />
        </div>
      )}
      <Card className="text-center space-y-3">
        <span className="w-12 h-12 rounded-2xl bg-emerald/10 text-emerald flex items-center justify-center mx-auto">
          {outcome.hasIssue ? <MessageSquareWarning className="w-6 h-6" /> : <Heart className="w-6 h-6" />}
        </span>
        <p className="text-sm text-foreground">{outcome.message ?? (outcome.hasIssue ? 'Chúng mình đã ghi nhận vấn đề bạn gặp.' : 'Cảm ơn bạn đã đánh giá dịch vụ.')}</p>
        <div className="flex flex-col sm:flex-row justify-center gap-2">
          {outcome.hasIssue && workshop.hotline && !outcome.safetyAdvice && <CallButton hotline={workshop.hotline} label="Liên hệ xưởng" />}
          <Button variant="secondary" onClick={() => navigate('/dashboard')}>
            Về trang chủ
          </Button>
        </div>
      </Card>
    </div>
  )
}

/** SCR-901 — post-service survey (`/follow-ups/:followUpId`), opened from the in-app notification feed. */
export default function FollowUp() {
  const { followUpId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const [data, setData] = useState<FollowUpData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [rating, setRating] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [ratingError, setRatingError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [outcome, setOutcome] = useState<FollowUpOutcome | null>(null)
  const [closedHotline, setClosedHotline] = useState<string | null>(null)
  const viewed = useRef(false)

  const load = useCallback(
    () =>
      getFollowUp(followUpId)
        .then(result => {
          setData(result)
          setError(null)
          if (result.outcome) setOutcome(result.outcome)
          if (!viewed.current) {
            viewed.current = true
            track('follow_up_viewed', { status: result.status, canRespond: result.canRespond, source: location.key === 'default' ? 'link' : 'app' })
          }
        })
        .catch((reason: unknown) => setError(isApiError(reason) ? reason : null)),
    [followUpId, location.key],
  )

  useEffect(() => {
    void load()
  }, [load])

  const back = () => (location.key === 'default' ? navigate('/dashboard') : navigate(-1))

  async function submit() {
    if (!data || submitting) return
    if (!rating) {
      setRatingError('Vui lòng chọn số sao.')
      return
    }
    setRatingError(null)
    setSubmitting(true)
    try {
      const result = await respondFollowUp(data.followUpId, { rating, comment: comment.trim() || null })
      setOutcome(result.outcome)
      setData({ ...data, status: 'CLOSED', canRespond: false, response: { rating, comment: comment.trim() || null, respondedAt: new Date().toISOString() } })
      track('follow_up_submitted', {
        rating,
        hasComment: Boolean(comment.trim()),
        hasIssue: result.outcome.hasIssue,
        safetyAdvice: result.outcome.safetyAdvice,
      })
    } catch (reason) {
      const code = isApiError(reason) ? reason.code : 'UNKNOWN'
      track('follow_up_submit_failed', { errorCode: code })
      if (code === 'FOLLOW_UP_ALREADY_RESPONDED') void load()
      else if (code === 'FOLLOW_UP_CLOSED') setClosedHotline(isApiError(reason) ? String(reason.details?.workshopHotline ?? data.workshop.hotline) : data.workshop.hotline)
      else if (code === 'FOLLOW_UP_NOT_OPEN') void load()
      else toast.show('Tạm thời chưa gửi được, bạn thử lại nhé.', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (error && !data) {
    return (
      <div className="p-4 sm:p-6 max-w-xl mx-auto">
        <Card>
          {isApiError(error, 'FOLLOW_UP_NOT_FOUND') ? (
            <EmptyState title="Không tìm thấy khảo sát" action={<Button onClick={() => navigate('/dashboard')}>Về trang chủ</Button>} />
          ) : (
            <ErrorState traceId={error.traceId} onRetry={() => void load()} />
          )}
        </Card>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="p-4 sm:p-6 max-w-xl mx-auto space-y-4" aria-busy>
        <SkeletonCard lines={2} />
        <SkeletonCard lines={3} />
      </div>
    )
  }

  const closed = closedHotline !== null || (data.status === 'CLOSED' && data.closedReason === 'NO_RESPONSE')
  const lowRating = rating !== null && rating <= 2

  return (
    <div className="p-4 sm:p-6 max-w-xl mx-auto space-y-4 pb-28 sm:pb-6">
      <button type="button" onClick={back} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Quay lại
      </button>
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Đánh giá dịch vụ</h1>

      <Card className="flex items-center gap-3">
        <span className="w-10 h-10 rounded-xl bg-emerald/10 text-emerald flex items-center justify-center shrink-0">
          <CalendarCheck2 className="w-5 h-5" />
        </span>
        <div className="min-w-0 text-sm">
          <p className="font-semibold text-foreground truncate">{data.workshop.name}</p>
          <p className="text-muted">
            {formatDate(data.booking.bookingDate)}
            {data.booking.bookingCode ? ` · ${data.booking.bookingCode}` : ''}
          </p>
        </div>
      </Card>

      {closed ? (
        <Card className="text-center space-y-3">
          <Clock className="w-8 h-8 text-muted mx-auto" />
          <p className="text-sm text-foreground">
            Khảo sát đã đóng. Nếu xe có vấn đề, vui lòng liên hệ xưởng {data.workshop.name} — {closedHotline ?? data.workshop.hotline}.
          </p>
          <CallButton hotline={closedHotline ?? data.workshop.hotline} />
        </Card>
      ) : data.status === 'PENDING' ? (
        <Card>
          <EmptyState icon={<Clock className="w-5 h-5" />} title="Chưa tới lúc đánh giá." description="Bạn sẽ nhận lời mời sau khi dịch vụ hoàn tất." />
        </Card>
      ) : outcome ? (
        <>
          {data.response && (
            <Card className="space-y-1">
              <p className="text-xs text-muted">Đánh giá của bạn</p>
              <p className="text-sm text-foreground">
                {'★'.repeat(data.response.rating)}
                <span className="text-muted">{'★'.repeat(5 - data.response.rating)}</span> · {RATING_LABELS[data.response.rating - 1]}
              </p>
              {data.response.comment && <p className="text-sm text-muted whitespace-pre-wrap">{data.response.comment}</p>}
            </Card>
          )}
          <ResultPanel outcome={outcome} workshop={data.workshop} />
        </>
      ) : (
        <Card className="space-y-5">
          <p className="text-base text-foreground">{data.question}</p>
          <StarRating value={rating} onChange={value => { setRating(value); setRatingError(null) }} disabled={submitting} error={ratingError} />
          <TextArea
            label="Nhận xét"
            optional
            rows={4}
            maxLength={MAX_COMMENT}
            value={comment}
            disabled={submitting}
            placeholder={lowRating ? 'Bạn gặp vấn đề gì? Mô tả giúp xưởng nhé.' : 'Chia sẻ thêm về trải nghiệm của bạn (không bắt buộc)'}
            onChange={event => setComment(event.target.value.slice(0, MAX_COMMENT))}
            aside={<span className="text-xs text-muted font-mono">{comment.length}/{MAX_COMMENT}</span>}
          />
          <div className="fixed sm:static bottom-0 inset-x-0 lg:left-60 z-20 bg-surface/95 sm:bg-transparent backdrop-blur sm:backdrop-blur-none border-t border-border sm:border-0 px-4 py-3 sm:p-0">
            <Button fullWidth size="lg" disabled={!data.canRespond} loading={submitting} loadingText="Đang gửi…" onClick={() => void submit()}>
              Gửi đánh giá
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
