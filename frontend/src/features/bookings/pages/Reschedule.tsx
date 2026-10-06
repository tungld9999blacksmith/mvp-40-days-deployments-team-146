import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CalendarSync, Store, Timer } from 'lucide-react'
import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Skeleton, { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { cn } from '@/shared/ui/cn'
import { formatCountdown } from '@/shared/utils/format'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { getBooking, getRescheduleAvailability, rescheduleBooking } from '../api'
import { invalidateUpcomingBookings } from '../hooks/useUpcomingBookings'
import AlternativesSheet from '../components/AlternativesSheet'
import { DayStrip, SlotGrid, type DayState } from '../components/SlotPicker'
import type { Alternative, BookingDetail, BookingSource, Slot } from '../types'
import { bookableDays, formatLongDay, isPastSlot, secondsLeft, slotLabel, tokenExpiry } from '../utils'

interface Draft {
  date: string
  timeSlot: string
  confirmationToken: string
  expiresAt: number
  /** One key per token; a retry after a network error reuses it (FF EF-1204). */
  idempotencyKey: string
}

const BLOCKED: Record<string, string> = {
  TOO_CLOSE_TO_APPOINTMENT: 'Đã quá hạn đổi lịch (trước giờ hẹn 60 phút). Vui lòng liên hệ xưởng.',
  MAX_RESCHEDULES_REACHED: 'Bạn đã đổi lịch tối đa 2 lần cho lịch hẹn này.',
}

function dayStateOf(slots: Slot[], day: string): DayState {
  if (slots.length === 0) return 'closed'
  const upcoming = slots.filter(slot => !isPastSlot(day, slot.timeSlot))
  if (upcoming.length === 0) return 'past'
  return upcoming.some(slot => slot.available) ? 'open' : 'full'
}

function SlotColumn({ title, date, timeSlot, highlight }: { title: string; date: string; timeSlot: string; highlight?: boolean }) {
  return (
    <div className={cn('flex-1 rounded-2xl border p-4', highlight ? 'border-emerald/40 bg-emerald/5' : 'border-border bg-card')}>
      <p className="text-xs text-muted">{title}</p>
      <p className={cn('text-lg font-semibold mt-1', highlight ? 'text-emerald' : 'text-foreground')}>{slotLabel(timeSlot)}</p>
      <p className="text-sm text-muted">{formatLongDay(date)}</p>
    </div>
  )
}

/** No `RESCHEDULE` in `allowedActions` ⇒ back to the ticket with the reason (us-053 §8). */
function BlockedRedirect({ to, message }: { to: string; message: string | null }) {
  const toast = useToast()
  const shown = useRef(false)
  useEffect(() => {
    if (message && !shown.current) toast.show(message, 'warning')
    shown.current = true
  }, [message, toast])
  return <Navigate to={to} replace />
}

/** SCR-1203 / SCR-1204 — reschedule within the same workshop (us-053 §4.6, §4.7). */
export default function Reschedule() {
  const { bookingId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const source: BookingSource = searchParams.get('src') === 'REMINDER_24H' ? 'REMINDER_24H' : 'APP'
  const ticketPath = `/bookings/${encodeURIComponent(bookingId)}`

  const [booking, setBooking] = useState<BookingDetail | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const days = useRef(bookableDays()).current
  const [states, setStates] = useState<Record<string, DayState>>({})
  const [slotsByDay, setSlotsByDay] = useState<Record<string, Slot[]>>({})
  const [day, setDay] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [alternatives, setAlternatives] = useState<Alternative[] | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [networkFailed, setNetworkFailed] = useState(false)
  const [left, setLeft] = useState(0)
  const [reload, setReload] = useState(0)
  const started = useRef(false)

  useEffect(() => {
    getBooking(bookingId)
      .then(data => {
        setBooking(data)
        if (!started.current) {
          started.current = true
          track('reschedule_started', { code: null, source })
        }
      })
      .catch((reason: unknown) => setLoadError(isApiError(reason) ? reason : null))
  }, [bookingId, source])

  // Days load one after another (same reason as the booking flow: BK-02 is slow under load).
  useEffect(() => {
    if (!booking || !booking.allowedActions.includes('RESCHEDULE')) return
    let cancelled = false
    const controller = new AbortController()
    setStates({})
    ;(async () => {
      for (const date of days) {
        if (cancelled) return
        try {
          const data = await getRescheduleAvailability({ workshopId: booking.workshop.workshopId, bookingId, date, signal: controller.signal })
          if (cancelled) return
          setSlotsByDay(previous => ({ ...previous, [date]: data.slots }))
          setStates(previous => ({ ...previous, [date]: dayStateOf(data.slots, date) }))
        } catch (reason) {
          if (cancelled) return
          if (isApiError(reason, 'RESCHEDULE_NOT_ALLOWED')) {
            toast.show('Lịch hẹn này không đổi được nữa.', 'warning')
            navigate(ticketPath, { replace: true })
            return
          }
          setStates(previous => ({ ...previous, [date]: 'error' }))
        }
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [booking, bookingId, days, reload, navigate, ticketPath, toast])

  useEffect(() => {
    if (day || !booking) return
    const preferred = days.includes(booking.bookingDate) ? booking.bookingDate : null
    const first = days.find(item => states[item] === 'open')
    if (preferred && states[preferred] && states[preferred] !== 'closed') setDay(preferred)
    else if (first) setDay(first)
  }, [booking, day, days, states])

  useEffect(() => {
    if (!draft) return
    setLeft(secondsLeft(draft.expiresAt))
    const timer = window.setInterval(() => setLeft(secondsLeft(draft.expiresAt)), 1000)
    return () => window.clearInterval(timer)
  }, [draft])

  // Token expired on the confirm step ⇒ back to the slots, reloaded (§4.7).
  // Read the expiry itself: `left` is still 0 on the render that opens the step.
  useEffect(() => {
    if (draft && secondsLeft(draft.expiresAt) === 0 && !submitting) {
      setDraft(null)
      toast.show('Thẻ đổi lịch đã hết hạn, bạn chọn lại khung giờ nhé.', 'warning')
      setReload(count => count + 1)
    }
  }, [draft, left, submitting, toast])

  const requestSlot = useCallback(
    async (date: string, timeSlot: string) => {
      if (!booking) return
      setPending(slotLabel(timeSlot))
      try {
        const data = await getRescheduleAvailability({ workshopId: booking.workshop.workshopId, bookingId, date, timeSlot: slotLabel(timeSlot) })
        const requested = data.requested
        if (requested?.available && requested.confirmationToken) {
          setNetworkFailed(false)
          setDraft({
            date,
            timeSlot: requested.timeSlot,
            confirmationToken: requested.confirmationToken,
            expiresAt: tokenExpiry(Date.now()),
            idempotencyKey: newId(),
          })
        } else {
          setAlternatives(data.alternatives)
        }
      } catch (reason) {
        if (isApiError(reason, 'RESCHEDULE_SAME_SLOT')) toast.show('Đây là giờ hẹn hiện tại của bạn.', 'info')
        else if (isApiError(reason, 'RESCHEDULE_NOT_ALLOWED')) navigate(ticketPath, { replace: true })
        else toast.show('Chưa kiểm tra được khung giờ, bạn thử lại nhé.', 'error')
      } finally {
        setPending(null)
      }
    },
    [booking, bookingId, navigate, ticketPath, toast],
  )

  if (loadError) {
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-2xl mx-auto">
        <Card>
          {isApiError(loadError, 'BOOKING_NOT_FOUND') ? (
            <EmptyState title="Không tìm thấy lịch hẹn" action={<Button onClick={() => navigate('/bookings')}>Lịch hẹn của tôi</Button>} />
          ) : (
            <ErrorState traceId={loadError.traceId} onRetry={() => window.location.reload()} />
          )}
        </Card>
      </div>
    )
  }
  if (!booking) {
    return (
      <div className="p-4 sm:p-6 xl:p-8 max-w-2xl mx-auto space-y-4" aria-busy>
        <SkeletonCard lines={2} />
        <SkeletonCard lines={4} />
      </div>
    )
  }
  if (!booking.allowedActions.includes('RESCHEDULE')) {
    return <BlockedRedirect to={ticketPath} message={booking.rescheduleBlockedReason ? BLOCKED[booking.rescheduleBlockedReason] ?? null : null} />
  }

  const current = booking

  async function confirm() {
    if (!draft || submitting) return
    setSubmitting(true)
    try {
      await rescheduleBooking(current.bookingId, { confirmationToken: draft.confirmationToken, source }, draft.idempotencyKey)
      track('reschedule_succeeded', { code: null, source })
      invalidateUpcomingBookings()
      toast.show('Đã đổi lịch.', 'success')
      navigate(ticketPath, { replace: true })
    } catch (reason) {
      const code = isApiError(reason) ? reason.code : 'UNKNOWN'
      track('reschedule_failed', { code, source })
      if (code === NETWORK_ERROR || code === TIMEOUT_ERROR) {
        // Never claim success: read the ticket to see what really happened (EF-1204).
        try {
          const fresh = await getBooking(current.bookingId)
          if (fresh.bookingDate === draft.date && slotLabel(fresh.timeSlot) === slotLabel(draft.timeSlot)) {
            toast.show('Đã đổi lịch.', 'success')
            navigate(ticketPath, { replace: true })
            return
          }
        } catch {
          // still offline: keep the draft and the same key for a retry
        }
        setNetworkFailed(true)
        return
      }
      if (code === 'SLOT_FULL') {
        toast.show('Khung này vừa hết chỗ. Lịch cũ của bạn vẫn giữ nguyên.', 'warning')
        const list = isApiError(reason) ? reason.details?.alternatives : null
        setDraft(null)
        setAlternatives(Array.isArray(list) ? (list as Alternative[]) : [])
        setReload(count => count + 1)
      } else if (code === 'CONFIRMATION_TOKEN_EXPIRED' || code === 'INVALID_CONFIRMATION_TOKEN') {
        toast.show('Thẻ đổi lịch đã hết hiệu lực, bạn chọn lại khung giờ nhé.', 'warning')
        setDraft(null)
        setReload(count => count + 1)
      } else if (code === 'BOOKING_CHANGED' || code === 'BOOKING_NOT_CONFIRMED') {
        toast.show('Lịch hẹn vừa thay đổi.', 'warning')
        navigate(ticketPath, { replace: true })
      } else if (code === 'RESCHEDULE_TOO_LATE' || code === 'RESCHEDULE_LIMIT_REACHED') {
        toast.show(BLOCKED[code === 'RESCHEDULE_TOO_LATE' ? 'TOO_CLOSE_TO_APPOINTMENT' : 'MAX_RESCHEDULES_REACHED'], 'warning')
        navigate(ticketPath, { replace: true })
      } else {
        toast.show('Tạm thời chưa đổi được, lịch cũ vẫn giữ nguyên. Thử lại sau.', 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const slots = day ? slotsByDay[day] ?? null : null
  const visibleSlots = day && slots ? slots.filter(slot => !isPastSlot(day, slot.timeSlot)) : []

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-3xl mx-auto space-y-5">
      <Link to={ticketPath} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Lịch hẹn
      </Link>
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
          <CalendarSync className="w-6 h-6 text-emerald" /> Đổi lịch tại {current.workshop.name}
        </h1>
        <p className="text-muted mt-1">
          Giờ hiện tại: {slotLabel(current.timeSlot)} · {formatLongDay(current.bookingDate)}
        </p>
      </div>

      {draft ? (
        <Card className="space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <SlotColumn title="Hiện tại" date={current.bookingDate} timeSlot={current.timeSlot} />
            <ArrowRight className="w-5 h-5 text-muted self-center rotate-90 sm:rotate-0 shrink-0" />
            <SlotColumn title="Mới" date={draft.date} timeSlot={draft.timeSlot} highlight />
          </div>
          <p className="text-sm text-muted">Lịch cũ chỉ được huỷ khi lịch mới được giữ thành công. Mã lịch hẹn và QR giữ nguyên.</p>
          {networkFailed && (
            <Notice tone="warning" title="Chưa đổi được do mất kết nối">
              Lịch cũ của bạn vẫn giữ nguyên. Kiểm tra mạng rồi bấm xác nhận lại.
            </Notice>
          )}
          <div className={cn('flex items-center gap-2 text-sm rounded-xl px-3 py-2 border', left <= 60 ? 'text-warning border-warning/20 bg-warning/10' : 'text-muted border-border')}>
            <Timer className="w-4 h-4" /> Thẻ đổi lịch còn hiệu lực {formatCountdown(left)}
          </div>
          <div className="flex flex-col-reverse sm:flex-row gap-2">
            <Button variant="secondary" onClick={() => setDraft(null)} disabled={submitting}>
              Chọn khung khác
            </Button>
            <Button className="sm:flex-1" loading={submitting} loadingText="Đang đổi…" onClick={() => void confirm()}>
              Xác nhận đổi
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="space-y-5">
          <DayStrip days={days} states={states} selected={day} onSelect={setDay} />
          {!day || !slots ? (
            <div className="grid grid-cols-3 lg:grid-cols-6 gap-2" aria-busy>
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} className="h-14" />
              ))}
            </div>
          ) : visibleSlots.length === 0 ? (
            <p className="text-sm text-muted text-center py-6">{states[day] === 'closed' ? 'Xưởng nghỉ ngày này.' : 'Ngày này không còn khung giờ.'}</p>
          ) : (
            <SlotGrid
              slots={visibleSlots}
              selected={null}
              pending={pending}
              currentSlot={day === current.bookingDate ? slotLabel(current.timeSlot) : null}
              onSelect={slot => void requestSlot(day, slot.timeSlot)}
            />
          )}
        </Card>
      )}

      <p className="text-sm text-muted flex items-start gap-2">
        <Store className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Muốn đổi sang xưởng khác? Bạn cần huỷ lịch này và đặt mới.{' '}
          <Link to={ticketPath} className="text-emerald font-medium hover:text-emerald-bright">
            Về lịch hẹn
          </Link>
        </span>
      </p>

      <AlternativesSheet
        open={alternatives !== null}
        alternatives={alternatives ?? []}
        onPick={alternative => {
          setAlternatives(null)
          setDay(alternative.date)
          void requestSlot(alternative.date, alternative.timeSlot)
        }}
        onClose={() => setAlternatives(null)}
      />
    </div>
  )
}
