import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { CalendarClock, CalendarPlus, ChevronRight, Store } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import Spinner from '@/shared/ui/Spinner'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { page } from '@/shared/ui/page'
import { useMediaQuery, XL_QUERY } from '@/shared/hooks/useMediaQuery'
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatVnd } from '@/features/estimate/utils'
import { useCurrentVehicle } from '@/features/vehicles/currentVehicle/CurrentVehicleContext'
import { listMyBookings } from '../api'
import BookingPreview from '../components/BookingPreview'
import type { MyBookingItem } from '../types'
import { dayChip, previewedBookingId, slotLabel } from '../utils'

type Scope = 'UPCOMING' | 'PAST'

/**
 * `showVehicle`: the owner has several vehicles, so each row names its car.
 * `onPreview` (xl): the row opens the side preview instead of the ticket page.
 */
function BookingRow({
  item,
  showVehicle,
  selected,
  onPreview,
}: {
  item: MyBookingItem
  showVehicle: boolean
  selected?: boolean
  onPreview?: () => void
}) {
  const chip = dayChip(item.bookingDate)
  const status = BOOKING_STATUS[item.status]
  return (
    <Link
      to={`/bookings/${encodeURIComponent(item.bookingId)}`}
      onClick={
        onPreview
          ? event => {
              event.preventDefault()
              onPreview()
            }
          : undefined
      }
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'group flex items-center gap-4 bg-card border border-border rounded-2xl p-4 elevation-sm hover:border-emerald/30 hover:-translate-y-0.5 hover:elevation-md transition-all',
        selected && 'border-emerald ring-1 ring-emerald hover:border-emerald',
      )}
    >
      <span className="w-14 shrink-0 rounded-xl bg-emerald/10 text-emerald text-center py-2">
        <span className="block text-[11px] font-semibold uppercase">{chip.weekday}</span>
        <span className="block text-sm font-bold">{chip.dayMonth}</span>
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-semibold text-foreground">{slotLabel(item.timeSlot)}</span>
        <span className="flex items-center gap-1 text-xs text-muted mt-0.5 truncate">
          <Store className="w-3.5 h-3.5 shrink-0" />
          {item.workshop.name}
        </span>
        {showVehicle && item.vehicle && (
          <span className="block text-xs text-muted mt-0.5 truncate">
            {/* Plate first: it is what tells the cars apart when the line is cut on phones. */}
            <span className="font-mono">{item.vehicle.plateMasked}</span> · {item.vehicle.modelName}
          </span>
        )}
      </span>
      <span className="text-right shrink-0">
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
        {item.cost.amount !== null && (
          <span className="block font-mono text-xs text-muted mt-1.5">
            {item.cost.label === 'APPROVED_QUOTE' ? 'Báo giá ' : '~ '}
            {formatVnd(item.cost.amount)}
          </span>
        )}
      </span>
      <ChevronRight className="w-4 h-4 text-muted shrink-0 group-hover:translate-x-0.5 transition-transform" />
    </Link>
  )
}

/** SCR-1202 — Lịch của tôi (API-BT-01): upcoming ascending, past descending (last 90 days). */
export default function MyBookings() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const scope: Scope = searchParams.get('scope') === 'PAST' ? 'PAST' : 'UPCOMING'
  const [items, setItems] = useState<MyBookingItem[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const sentinel = useRef<HTMLDivElement>(null)
  const showVehicle = (useCurrentVehicle().vehicles?.length ?? 0) > 1
  // xl: list on the left, the chosen booking previewed on the right (DESIGN.md 2026-10-11).
  const wide = useMediaQuery(XL_QUERY)
  const [chosen, setChosen] = useState<string | null>(null)
  const previewId = wide && items ? previewedBookingId(items, chosen) : null

  const load = useCallback(
    async (from: string | null) => {
      try {
        const page = await listMyBookings(scope, from)
        setItems(previous => (from && previous ? [...previous, ...page.items] : page.items))
        setCursor(page.nextCursor)
        setError(null)
      } catch (reason) {
        setError(isApiError(reason) ? reason : null)
      }
    },
    [scope],
  )

  useEffect(() => {
    setItems(null)
    setCursor(null)
    void load(null)
  }, [load])

  // Infinite list: load the next page when the end of the list scrolls into view.
  useEffect(() => {
    const node = sentinel.current
    if (!node || !cursor) return
    const observer = new IntersectionObserver(async entries => {
      if (!entries[0]?.isIntersecting || loadingMore) return
      setLoadingMore(true)
      await load(cursor)
      setLoadingMore(false)
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [cursor, load, loadingMore])

  return (
    <div className={`${page('reading')} xl:max-w-none`}>
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Lịch hẹn của tôi</h1>
          <p className="text-muted mt-1">Mã lịch hẹn, QR check-in, đổi hoặc huỷ lịch.</p>
        </div>
        <Button icon={<CalendarPlus className="w-4 h-4" />} onClick={() => navigate('/booking')}>
          Đặt lịch
        </Button>
      </div>

      <div className="xl:grid xl:grid-cols-3 xl:gap-6 xl:items-start">
        <div className="xl:col-span-2 min-w-0">
      <div className="inline-flex p-1 rounded-xl bg-card border border-border mb-4" role="tablist" aria-label="Lịch hẹn">
        {(['UPCOMING', 'PAST'] as const).map(key => (
          <button
            key={key}
            role="tab"
            aria-selected={scope === key}
            onClick={() => setSearchParams(key === 'PAST' ? { scope: 'PAST' } : {})}
            className={cn(
              'px-4 py-1.5 rounded-lg text-sm font-medium transition-colors',
              scope === key ? 'bg-emerald/10 text-emerald' : 'text-muted hover:text-foreground',
            )}
          >
            {key === 'UPCOMING' ? 'Sắp tới' : 'Đã qua'}
          </button>
        ))}
      </div>

      {items === null && !error ? (
        <div className="space-y-3" aria-busy>
          <SkeletonCard lines={1} />
          <SkeletonCard lines={1} />
        </div>
      ) : error && !items ? (
        <Card>
          <ErrorState title="Không tải được lịch hẹn." traceId={error.traceId} onRetry={() => void load(null)} />
        </Card>
      ) : items && items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<CalendarClock className="w-5 h-5" />}
            title={scope === 'UPCOMING' ? 'Bạn chưa có lịch hẹn nào' : 'Chưa có lịch hẹn nào trong 90 ngày qua'}
            action={scope === 'UPCOMING' ? <Button onClick={() => navigate('/booking')}>Đặt lịch</Button> : undefined}
          />
        </Card>
      ) : (
        <>
          <ul className="space-y-3">
            {items?.map(item => (
              <li key={item.bookingId}>
                <BookingRow
                  item={item}
                  showVehicle={showVehicle}
                  selected={item.bookingId === previewId}
                  onPreview={wide ? () => setChosen(item.bookingId) : undefined}
                />
              </li>
            ))}
          </ul>
          <div ref={sentinel} className="h-8 flex items-center justify-center">
            {loadingMore && <Spinner />}
          </div>
          {scope === 'PAST' && !cursor && <p className="text-xs text-muted text-center">Chỉ hiển thị 90 ngày gần nhất.</p>}
        </>
      )}
        </div>
        {/* Not sticky: with the QR the card is taller than most screens, so its actions would never scroll into view. */}
        {previewId && <BookingPreview bookingId={previewId} className="xl:mt-[52px]" />}
      </div>
    </div>
  )
}
