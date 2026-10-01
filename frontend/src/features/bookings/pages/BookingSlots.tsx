import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { CalendarX2, MapPin } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card, CardHeader } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { getAvailability, getNearbyWorkshops } from '../api'
import { useSlotRequest } from '../hooks/useSlotRequest'
import AlternativesSheet from '../components/AlternativesSheet'
import { DayStrip, SlotGrid, type DayState } from '../components/SlotPicker'
import { useBookingWizard } from '../context/BookingWizardContext'
import type { Slot } from '../types'
import { bookableDays, isPastSlot, pickDefaultDay } from '../utils'

interface DayResult {
  state: DayState
  slots: Slot[]
}

function dayState(all: Slot[], upcoming: Slot[]): DayState {
  if (all.length === 0) return 'closed'
  if (upcoming.length === 0) return 'past'
  return upcoming.some(slot => slot.available) ? 'open' : 'full'
}

/** SCR-403 — 7-day strip + slot grid of one workshop (API-BK-02). */
export default function BookingSlots() {
  const navigate = useNavigate()
  const toast = useToast()
  const { vehicle, params, searchFor, workshopById, rememberWorkshops } = useBookingWizard()
  const workshopId = params.workshopId
  const workshop = workshopById(workshopId)
  const days = useMemo(() => bookableDays(), [])
  const [results, setResults] = useState<Record<string, DayResult>>({})
  const [attempt, setAttempt] = useState(0)
  const { pending, alternatives, closeAlternatives, requestSlot } = useSlotRequest()

  // Workshop details when the page is opened directly (estimate / quote / reload).
  useEffect(() => {
    if (!workshopId || workshop) return
    let cancelled = false
    getNearbyWorkshops({ anchor: null, userVehicleId: vehicle.userVehicleId })
      .then(data => {
        if (!cancelled) rememberWorkshops(data.workshops)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [workshopId, workshop, vehicle.userVehicleId, rememberWorkshops])

  // Slots of every bookable day, one request at a time (the backend serialises them anyway):
  // the requested day first, then the others in order for the closed / full markers.
  // Read through a ref: changing the day must not reload the whole week.
  const firstDayRef = useRef<string | null>(null)
  firstDayRef.current = params.date && days.includes(params.date) ? params.date : null
  useEffect(() => {
    if (!workshopId) return
    const controller = new AbortController()
    setResults({})
    const firstDay = firstDayRef.current
    const order = firstDay ? [firstDay, ...days.filter(day => day !== firstDay)] : days
    void (async () => {
      for (const day of order) {
        if (controller.signal.aborted) return
        try {
          const data = await getAvailability({ workshopId, date: day, withAlternatives: false, signal: controller.signal })
          const slots = data.slots.filter(slot => !isPastSlot(day, slot.timeSlot, new Date()))
          setResults(previous => ({ ...previous, [day]: { state: dayState(data.slots, slots), slots } }))
        } catch (reason) {
          if (controller.signal.aborted) return
          setResults(previous => ({ ...previous, [day]: { state: 'error', slots: [] } }))
          if (isApiError(reason, 'WORKSHOP_NOT_FOUND')) {
            toast.show('Xưởng không còn nhận đặt lịch, bạn chọn xưởng khác nhé.', 'warning')
            return
          }
        }
      }
    })()
    return () => controller.abort()
  }, [workshopId, days, attempt, toast])

  const states = useMemo(
    () => Object.fromEntries(days.map(day => [day, results[day]?.state ?? 'loading'])) as Record<string, DayState>,
    [days, results],
  )
  const requestedDay = params.date && days.includes(params.date) && !['closed', 'past'].includes(states[params.date]) ? params.date : null
  const selectedDay = requestedDay ?? pickDefaultDay(days, states)
  const allLoaded = days.every(day => states[day] !== 'loading')
  const nothingFree = allLoaded && days.every(day => ['closed', 'past', 'full'].includes(states[day]))
  const allFailed = allLoaded && days.every(day => states[day] === 'error')
  const selected = selectedDay ? results[selectedDay] : undefined

  const selectDay = (day: string) => navigate(`/booking/slots${searchFor({ date: day, timeSlot: null })}`, { replace: true })

  if (!workshopId) return <Navigate to={`/booking/workshops${searchFor({})}`} replace />

  return (
    <div className="max-w-3xl space-y-5">
      <Card>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {workshop ? (
              <>
                <p className="text-sm font-semibold text-foreground truncate">{workshop.name}</p>
                {workshop.address && (
                  <p className="text-xs text-muted mt-1 flex items-start gap-1.5">
                    <MapPin className="w-3.5 h-3.5 shrink-0 mt-px" />
                    {workshop.address}
                  </p>
                )}
              </>
            ) : (
              <Skeleton className="h-4 w-48" />
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={() => navigate(`/booking/workshops${searchFor({ workshopId: null, timeSlot: null })}`)}>
            Đổi xưởng
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="Chọn ngày" />
        <DayStrip days={days} states={states} selected={selectedDay} onSelect={selectDay} />
      </Card>

      <Card>
        <CardHeader title="Chọn khung giờ" />
        {allFailed ? (
          <ErrorState compact title="Không tải được lịch của xưởng." description={null} onRetry={() => setAttempt(count => count + 1)} />
        ) : nothingFree ? (
          <EmptyState
            icon={<CalendarX2 className="w-5 h-5" />}
            title="Xưởng đã kín lịch 7 ngày tới."
            description="Bạn thử chọn xưởng khác nhé."
            action={<Button onClick={() => navigate(`/booking/workshops${searchFor({ workshopId: null, timeSlot: null })}`)}>Chọn xưởng khác</Button>}
          />
        ) : !selected || selected.state === 'loading' ? (
          <div className="grid grid-cols-3 lg:grid-cols-6 gap-2" aria-busy>
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-14 rounded-xl" />
            ))}
          </div>
        ) : selected.state === 'error' ? (
          <ErrorState compact title="Không tải được khung giờ ngày này." description={null} onRetry={() => setAttempt(count => count + 1)} />
        ) : (
          <SlotGrid
            slots={selected.slots}
            selected={params.timeSlot}
            pending={pending}
            onSelect={slot => selectedDay && void requestSlot({ workshopId, date: selectedDay, timeSlot: slot.timeSlot })}
          />
        )}
      </Card>

      <AlternativesSheet
        open={alternatives !== null}
        alternatives={alternatives ?? []}
        onPick={alternative => void requestSlot(alternative)}
        onClose={closeAlternatives}
      />
    </div>
  )
}
