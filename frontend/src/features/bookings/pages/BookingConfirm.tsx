import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import { getCostEstimate } from '@/features/estimate/api'
import { createBooking } from '../api'
import { invalidateUpcomingBookings } from '../hooks/useUpcomingBookings'
import AlternativesSheet from '../components/AlternativesSheet'
import BookingSummaryCard, { type SummaryCost } from '../components/BookingSummaryCard'
import { useBookingWizard } from '../context/BookingWizardContext'
import { useSlotRequest } from '../hooks/useSlotRequest'
import { useBookingMilestone } from './BookingLayout'
import type { Alternative, Booking } from '../types'
import { bookingErrorMessage } from '../utils'

/** Router state handed to the ticket screen (no GET /bookings/{id} yet — us-053). */
export interface TicketState {
  booking: Booking
  workshopAddress: string | null
}

const VEHICLE_ERRORS = ['FORBIDDEN', 'VEHICLE_NOT_FOUND', 'VEHICLE_NOT_ACTIVE', 'ONBOARDING_REQUIRED']

/** SCR-404 — summary card; the only place that creates a booking (API-BK-03). */
export default function BookingConfirm() {
  const navigate = useNavigate()
  const toast = useToast()
  const { vehicle, params, searchFor, workshopById, card, setCard, note, setNote, startedAt } = useBookingWizard()
  const status = useMaintenanceStatus(vehicle.userVehicleId)
  const milestone = useBookingMilestone()
  const { pending, alternatives, showAlternatives, closeAlternatives, requestSlot } = useSlotRequest()
  const [submitting, setSubmitting] = useState(false)
  const [blocking, setBlocking] = useState<'OPEN_BOOKING_EXISTS' | null>(null)
  const [cost, setCost] = useState<SummaryCost>({ kind: 'LOADING' })
  /** Booked: the card is cleared while the ticket opens; nothing may redirect back to the slots. */
  const booked = useRef(false)
  const cardWorkshop = card?.workshopId ?? null

  // FE §3.5 — the us-045 estimate of the same workshop + milestone.
  useEffect(() => {
    let cancelled = false
    const done = (value: SummaryCost) => !cancelled && setCost(value)
    setCost({ kind: 'LOADING' })
    if (cardWorkshop && milestone !== null) {
      getCostEstimate(vehicle.userVehicleId, { odoMilestone: milestone, workshopId: cardWorkshop })
        .then(estimate => done(estimate.status === 'READY' ? { kind: 'ESTIMATE', amount: estimate.chargeableTotal } : { kind: 'NONE' }))
        .catch(() => done({ kind: 'NONE' }))
    } else {
      done({ kind: 'NONE' })
    }
    return () => {
      cancelled = true
    }
  }, [cardWorkshop, milestone, vehicle.userVehicleId])

  if (booked.current) return null
  // Token lives in memory only: after a reload the owner picks the slot again (FE §10).
  if (!card || card.workshopId !== params.workshopId) {
    return <Navigate to={`/booking/slots${searchFor({ timeSlot: null })}`} replace />
  }
  const current = card

  const workshop = workshopById(current.workshopId)
  const next = status.data?.nextMilestone ?? null
  const items = next && (params.odoMilestone === null || params.odoMilestone === next.odoMilestoneKm) ? next.items : []

  const recheck = () => void requestSlot({ workshopId: current.workshopId, date: current.date, timeSlot: current.timeSlot })

  async function confirm() {
    setSubmitting(true)
    try {
      const booking = await createBooking(
        {
          confirmationToken: current.confirmationToken,
          ...(params.proposalId ? { proposalId: params.proposalId } : {}),
          userVehicleId: vehicle.userVehicleId,
          ...(milestone !== null ? { milestoneRef: String(milestone) } : {}),
          ...(note.trim() ? { note: note.trim() } : {}),
        },
        current.idempotencyKey,
      )
      track('booking_confirmed', {
        status: booking.status.toUpperCase(),
        secondsFromStart: Math.round((Date.now() - startedAt) / 1000),
      })
      booked.current = true
      setCard(null)
      setNote('')
      invalidateUpcomingBookings()
      const state: TicketState = { booking, workshopAddress: workshop?.address || null }
      navigate(`/bookings/${encodeURIComponent(booking.bookingId)}`, { replace: true, state })
    } catch (reason) {
      if (!isApiError(reason)) {
        toast.show('Tạm thời chưa đặt được, bạn thử lại giúp mình.', 'error')
        return
      }
      if (VEHICLE_ERRORS.includes(reason.code)) {
        navigate('/dashboard', { replace: true })
        return
      }
      if (reason.code === 'SLOT_FULL') {
        const list = reason.details?.alternatives
        showAlternatives(Array.isArray(list) ? (list as Alternative[]) : [])
        return
      }
      if (reason.code === 'HOLD_EXPIRED' || reason.code === 'INVALID_CONFIRMATION_TOKEN') {
        toast.show(bookingErrorMessage(reason.code) ?? '', 'warning')
        recheck()
        return
      }
      if (reason.code === 'OPEN_BOOKING_EXISTS') {
        setBlocking(reason.code)
        return
      }
      toast.show(bookingErrorMessage(reason.code) ?? 'Tạm thời chưa đặt được, bạn thử lại giúp mình.', 'error')
      // The token is spent by the attempt: fetch a fresh one for the same slot.
      recheck()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <BookingSummaryCard
        workshop={{ name: workshop?.name ?? 'Xưởng đã chọn', address: workshop?.address || null }}
        date={current.date}
        timeSlot={current.timeSlot}
        vehicle={vehicle}
        odoMilestone={milestone}
        items={items}
        cost={cost}
        tokenExpiresAt={current.expiresAt}
        submitting={submitting || pending !== null}
        note={note}
        onNoteChange={setNote}
        onConfirm={() => void confirm()}
        onEdit={() => navigate(`/booking/slots${searchFor({ timeSlot: null })}`)}
        onCancel={() => navigate(-1)}
        onRecheck={() => recheck()}
      />

      <AlternativesSheet
        open={alternatives !== null}
        alternatives={alternatives ?? []}
        onPick={alternative => void requestSlot(alternative)}
        onClose={() => {
          closeAlternatives()
          navigate(`/booking/slots${searchFor({ timeSlot: null })}`)
        }}
      />

      <Dialog
        open={blocking === 'OPEN_BOOKING_EXISTS'}
        onClose={() => setBlocking(null)}
        title="Bạn đang có lịch hẹn chưa hoàn tất"
        description="Mỗi xe chỉ có một lịch hẹn đang mở. Hoàn tất hoặc huỷ lịch hiện tại trước khi đặt lịch mới."
        footer={
          <>
            <Button variant="secondary" onClick={() => setBlocking(null)}>
              Đóng
            </Button>
            <Button onClick={() => navigate('/dashboard')}>Về trang chủ</Button>
          </>
        }
      />
    </div>
  )
}
