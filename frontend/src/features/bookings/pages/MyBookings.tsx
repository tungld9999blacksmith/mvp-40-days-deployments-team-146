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
import { BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatVnd } from '@/features/estimate/utils'
import { listMyBookings } from '../api'
import type { MyBookingItem } from '../types'
import { dayChip, slotLabel } from '../utils'

type Scope = 'UPCOMING' | 'PAST'

function BookingRow({ item }: { item: MyBookingItem }) {
  const chip = dayChip(item.bookingDate)
  const status = BOOKING_STATUS[item.status]
  return (
    <Link
      to={`/bookings/${encodeURIComponent(item.bookingId)}`}
      className="group flex items-center gap-4 bg-card border border-border rounded-2xl p-4 elevation-sm hover:border-emerald/30 hover:-translate-y-0.5 hover:elevation-md transition-all"
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
      </span>
      <span className="text-right shrink-0">
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
        {item.cost.amount !== null && (
          <span className="block font-mono text-xs text-muted mt-1.5">
            {'~ '}
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
    <div className="p-4 sm:p-6 xl:p-8 max-w-2xl">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Lịch hẹn của tôi</h1>
          <p className="text-muted mt-1">Mã lịch hẹn, QR check-in, đổi hoặc huỷ lịch.</p>
        </div>
        <Button icon={<CalendarPlus className="w-4 h-4" />} onClick={() => navigate('/booking')}>
          Đặt lịch
        </Button>
      </div>

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
                <BookingRow item={item} />
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
  )
}
