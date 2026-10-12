import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, QrCode } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { PORTAL_BOOKING_STATUS as BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatKm, formatLicensePlate, formatTimeDayMonth, formatWeekdayDate } from '@/shared/utils/format'
import { useWorkshopAuth } from '@/features/workshop-auth/context/WorkshopAuthContext'
import { slotLabel, todayVn } from '@/features/bookings/utils'
import { getBoard } from '@/features/workshop-board/api'
import type { BoardData } from '@/features/workshop-board/types'
import { formatVnd } from '@/features/estimate/utils'
import { listWorkshopQuotes } from '@/features/quotes/api'
import { usePricingFlow } from '@/features/booking-lines/flow'
import { awaitingOwnerItems } from '@/features/booking-lines/logic'
import type { WorkshopQuoteList } from '@/features/quotes/types'

/** Name + vehicle, then the badges: stacked on phones, one line from `sm`. */
const ROW_BODY = 'flex-1 min-w-0 flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-4'

/**
 * `/technician` — today's summary from API-WB-01 (first 5 bookings), plus quotes waiting for review (QT-11)
 * under `legacy` or extras waiting for the owner under `two_tier`, where no new quote is created.
 */
export default function TechnicianDashboard() {
  const navigate = useNavigate()
  const { displayName, workshop } = useWorkshopAuth()
  const [board, setBoard] = useState<BoardData | null>(null)
  const [boardError, setBoardError] = useState<ApiError | null>(null)
  const [quotes, setQuotes] = useState<WorkshopQuoteList | null>(null)
  // two_tier is the default flow, so it is assumed until /pricing-flow says legacy.
  const twoTier = usePricingFlow() !== 'legacy'

  const loadBoard = () => {
    const today = todayVn()
    setBoardError(null)
    getBoard({ from: today, to: today, statuses: [], q: '' })
      .then(setBoard)
      .catch((reason: unknown) => setBoardError(isApiError(reason) ? reason : null))
  }

  useEffect(() => {
    loadBoard()
  }, [])

  useEffect(() => {
    if (twoTier) return
    listWorkshopQuotes('PENDING_APPROVAL')
      .then(setQuotes)
      .catch(() => setQuotes(null))
  }, [twoTier])

  const summary = board?.summary
  const awaiting = board ? awaitingOwnerItems(board.items) : null
  // `attention`: a non-zero count needs the owner's action, so it reads in warning colour.
  const stats = [
    { label: 'Chờ xác nhận', value: summary?.PENDING, attention: true, to: '/technician/board?status=PENDING' },
    { label: 'Lịch hẹn hôm nay', value: board ? board.items.filter(item => item.status !== 'CANCELLED').length : undefined, attention: false, to: '/technician/board' },
    { label: 'Đang làm', value: summary ? summary.CHECKED_IN + summary.IN_PROGRESS : undefined, attention: false, to: '/technician/board?status=CHECKED_IN&status=IN_PROGRESS' },
    twoTier
      ? { label: 'Phát sinh chờ chủ xe', value: awaiting?.length, attention: true, to: '/technician/board?status=CHECKED_IN&status=IN_PROGRESS' }
      : { label: 'Báo giá chờ duyệt', value: quotes?.items.length, attention: true, to: '/technician/quotes' },
  ]

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-8">
        <div>
          <p className="text-xs font-medium text-muted first-letter:uppercase">{formatWeekdayDate(new Date())}</p>
          <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Xin chào{displayName ? ', ' : ''}
            {displayName && <span>{displayName}</span>}
          </h1>
          {workshop && <p className="text-muted mt-1.5">{workshop.name}</p>}
        </div>
        <Button icon={<QrCode className="w-4 h-4" />} onClick={() => navigate('/technician/check-in')}>
          Check-in QR
        </Button>
      </div>

      {/* One strip of count links, not KPI tiles: today's numbers are small (FINDING-015). */}
      <nav aria-label="Số liệu hôm nay" className="grid grid-cols-2 sm:grid-cols-4 gap-px mb-6 rounded-2xl overflow-hidden border border-border bg-border elevation-sm">
        {stats.map(({ label, value, attention, to }) => (
          <Link key={label} to={to} className="flex flex-col gap-1 px-4 py-3 sm:px-5 bg-card hover:bg-card-hover transition-colors">
            <span className="text-xs sm:text-sm text-muted">{label}</span>
            <span className={cn('font-mono text-xl sm:text-2xl font-bold leading-none', attention && value ? 'text-warning' : 'text-foreground')}>{value ?? '–'}</span>
          </Link>
        ))}
      </nav>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <span className="text-sm font-semibold text-foreground">Lịch hẹn hôm nay</span>
            <Link to="/technician/board" className="text-xs text-emerald font-medium hover:text-emerald-bright">
              Xem tất cả →
            </Link>
          </div>
          {boardError ? (
            <ErrorState compact traceId={boardError.traceId} onRetry={loadBoard} />
          ) : !board ? (
            <div className="p-5 space-y-3">
              {[0, 1, 2].map(index => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : board.items.length === 0 ? (
            <EmptyState title="Chưa có lịch hẹn nào hôm nay." />
          ) : (
            <ul className="divide-y divide-border">
              {board.items.slice(0, 5).map(item => (
                <li key={item.bookingId}>
                  <Link to={`/technician/board/${encodeURIComponent(item.bookingId)}`} className="px-5 py-3.5 flex items-center gap-4 hover:bg-card-hover transition-colors">
                    <span className="text-sm font-bold text-foreground font-mono w-12">{slotLabel(item.timeSlot)}</span>
                    {/* FINDING-021: on phones the badge sits under the name instead of truncating it. */}
                    <span className={ROW_BODY}>
                      <span className="min-w-0 sm:flex-1">
                        <span className="block text-sm font-medium text-foreground truncate">{item.customer.fullName}</span>
                        <span className="block text-xs text-muted truncate">
                          {item.vehicle.modelName} · {formatLicensePlate(item.vehicle.licensePlate)}
                        </span>
                      </span>
                      {BOOKING_STATUS[item.status] && (
                        <Badge tone={BOOKING_STATUS[item.status].tone} className="self-start sm:self-auto">
                          {BOOKING_STATUS[item.status].label}
                        </Badge>
                      )}
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {twoTier ? (
          <Card className="p-0 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <span className="text-sm font-semibold text-foreground">Phát sinh chờ chủ xe</span>
            </div>
            {!awaiting ? (
              <div className="p-5 space-y-3">
                {[0, 1].map(index => (
                  <Skeleton key={index} className="h-10 w-full" />
                ))}
              </div>
            ) : awaiting.length === 0 ? (
              <EmptyState title="Không có phát sinh nào chờ chủ xe." />
            ) : (
              <ul className="divide-y divide-border">
                {awaiting.slice(0, 5).map(item => (
                  <li key={item.bookingId}>
                    <Link to={`/technician/board/${encodeURIComponent(item.bookingId)}`} className="px-5 py-3.5 flex items-center gap-4 hover:bg-card-hover transition-colors">
                      <span className={ROW_BODY}>
                        <span className="min-w-0 sm:flex-1">
                          <span className="block text-sm font-medium text-foreground truncate">{item.customer.fullName}</span>
                          <span className="block text-xs text-muted truncate">
                            {item.vehicle.modelName} · {formatLicensePlate(item.vehicle.licensePlate)}
                          </span>
                        </span>
                        <span className="flex flex-wrap gap-1.5">
                          {(item.ownerReplyOverdue ?? 0) > 0 && <Badge tone="error">Cần gọi</Badge>}
                          <Badge tone="warning">{item.awaitingOwner} phát sinh</Badge>
                        </span>
                      </span>
                      <ChevronRight className="w-4 h-4 text-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ) : (
          <Card className="p-0 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <span className="text-sm font-semibold text-foreground">Báo giá chờ duyệt</span>
              <Link to="/technician/quotes" className="text-xs text-emerald font-medium hover:text-emerald-bright">
                Xem tất cả →
              </Link>
            </div>
            {!quotes ? (
              <div className="p-5 space-y-3">
                {[0, 1].map(index => (
                  <Skeleton key={index} className="h-10 w-full" />
                ))}
              </div>
            ) : quotes.items.length === 0 ? (
              <EmptyState title="Không có báo giá chờ duyệt." />
            ) : (
              <ul className="divide-y divide-border">
                {quotes.items.slice(0, 5).map(quote => (
                  <li key={quote.quoteId}>
                    <Link
                      to={`/technician/quote-review?quoteId=${encodeURIComponent(quote.quoteId)}`}
                      className="px-5 py-3.5 flex items-center gap-4 hover:bg-card-hover transition-colors"
                    >
                      <span className={ROW_BODY}>
                        <span className="min-w-0 sm:flex-1">
                          <span className="block text-sm font-medium text-foreground truncate">
                            {quote.modelName} · <span className="font-mono">{formatLicensePlate(quote.plateNumber)}</span>
                          </span>
                          <span className="block text-xs text-muted truncate">
                            {quote.customer.fullName} · Mốc {formatKm(quote.odoMilestone)} · gửi {quote.submittedAt ? formatTimeDayMonth(quote.submittedAt) : '—'}
                          </span>
                        </span>
                        <span className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                          <span className="font-mono text-sm text-foreground">{formatVnd(quote.estimatedTotal)}</span>
                          {quote.isWaitingLong && <Badge tone="error">Chờ &gt; 24h</Badge>}
                        </span>
                      </span>
                      <ChevronRight className="w-4 h-4 text-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
