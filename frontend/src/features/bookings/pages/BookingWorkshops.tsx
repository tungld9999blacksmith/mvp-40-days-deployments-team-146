import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapPinOff } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import { Card } from '@/shared/ui/Card'
import { SelectInput } from '@/shared/ui/Field'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { getNearbyWorkshops } from '../api'
import LocationAnchorPicker from '../components/LocationAnchorPicker'
import WorkshopCard from '../components/WorkshopCard'
import { useBookingWizard } from '../context/BookingWizardContext'
import type { NearbyData, NearbyWorkshop } from '../types'
import { bookableDays, bookingErrorMessage, dayChip, isBookableDay, tokenExpiry } from '../utils'

/** Hourly starts shown in the optional "Giờ" filter (backend slot length defaults to 60 min). */
const TIME_OPTIONS = Array.from({ length: 12 }, (_, index) => `${String(7 + index).padStart(2, '0')}:00`)

/** SCR-402 — ranked workshops near the anchor (API-BK-01). */
export default function BookingWorkshops() {
  const navigate = useNavigate()
  const { vehicle, params, searchFor, anchor, setAnchor, rememberWorkshops, setCard } = useBookingWizard()
  const [date, setDate] = useState<string>(params.date && isBookableDay(params.date) ? params.date : '')
  const [time, setTime] = useState<string>(params.timeSlot ?? '')
  const [data, setData] = useState<NearbyData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getNearbyWorkshops({
      anchor,
      userVehicleId: vehicle.userVehicleId,
      date: date || null,
      timeSlot: date && time ? time : null,
    })
      .then(result => {
        if (cancelled) return
        setData(result)
        rememberWorkshops(result.workshops)
      })
      .catch((reason: unknown) => {
        if (cancelled) return
        setData(null)
        setError(isApiError(reason) ? reason : null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [anchor, vehicle.userVehicleId, date, time, attempt, rememberWorkshops])

  const select = useCallback(
    (workshop: NearbyWorkshop, rank: number) => {
      track('booking_workshop_selected', {
        rankedBy: data?.anchor.rankedBy ?? null,
        isPreferred: workshop.isPreferred,
        rank: rank + 1,
      })
      const slot = workshop.availability
      if (slot?.available && slot.confirmationToken) {
        // Date + time already chosen and free: the token is ready, go straight to the card.
        setCard({
          workshopId: workshop.workshopId,
          date: slot.date,
          timeSlot: slot.timeSlot,
          confirmationToken: slot.confirmationToken,
          expiresAt: tokenExpiry(Date.now()),
          idempotencyKey: newId(),
        })
        navigate(`/booking/confirm${searchFor({ workshopId: workshop.workshopId, date: slot.date, timeSlot: time })}`)
        return
      }
      navigate(`/booking/slots${searchFor({ workshopId: workshop.workshopId, date: date || null, timeSlot: null })}`)
    },
    [data, date, time, navigate, searchFor, setCard],
  )

  const anchorRequired = isApiError(error, 'LOCATION_ANCHOR_REQUIRED')
  const noWorkshop = isApiError(error, 'WORKSHOP_NOT_FOUND') || isApiError(error, 'NO_WORKSHOP_AVAILABLE') || data?.workshops.length === 0

  return (
    <div className="max-w-3xl space-y-4">
      <LocationAnchorPicker resolved={data?.anchor ?? null} value={anchor} onChange={setAnchor} forceOpen={anchorRequired} />

      <div className="grid grid-cols-2 gap-3">
        <SelectInput label="Ngày muốn đến" optional value={date} onChange={event => setDate(event.target.value)}>
          <option value="">Bất kỳ</option>
          {bookableDays().map(day => {
            const chip = dayChip(day)
            return (
              <option key={day} value={day}>
                {chip.weekday} {chip.dayMonth}
              </option>
            )
          })}
        </SelectInput>
        <SelectInput label="Giờ" optional value={time} disabled={!date} onChange={event => setTime(event.target.value)}>
          <option value="">Bất kỳ</option>
          {TIME_OPTIONS.map(option => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </SelectInput>
      </div>

      {data?.anchor.rankedBy === 'REGION' && data.workshops.length > 0 && (
        <p className="text-xs text-muted">Sắp xếp theo khu vực (chưa có toạ độ để tính khoảng cách).</p>
      )}

      {loading ? (
        <div className="space-y-3" aria-busy>
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      ) : anchorRequired ? (
        <Card>
          <EmptyState icon={<MapPinOff className="w-5 h-5" />} title={bookingErrorMessage('LOCATION_ANCHOR_REQUIRED') ?? ''} description="Nhập địa điểm hoặc dùng vị trí hiện tại ở trên." />
        </Card>
      ) : noWorkshop ? (
        <Card>
          <EmptyState icon={<MapPinOff className="w-5 h-5" />} title="Chưa có xưởng khả dụng gần vị trí này." description="Bạn thử đổi vị trí nhé." />
        </Card>
      ) : error || !data ? (
        <Card>
          <ErrorState
            title="Không tải được danh sách xưởng."
            description={error ? bookingErrorMessage(error.code) ?? 'Vui lòng thử lại.' : 'Vui lòng thử lại.'}
            traceId={error?.traceId}
            onRetry={() => setAttempt(count => count + 1)}
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {data.workshops.map((workshop, rank) => (
            <li key={workshop.workshopId}>
              <WorkshopCard workshop={workshop} onSelect={item => select(item, rank)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
