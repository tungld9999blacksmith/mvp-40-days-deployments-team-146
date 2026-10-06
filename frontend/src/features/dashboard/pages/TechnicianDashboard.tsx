import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlarmClock, CalendarClock, ChevronRight, QrCode, Wrench } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { PORTAL_BOOKING_STATUS as BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatLicensePlate } from '@/shared/utils/format'
import { useWorkshopAuth } from '@/features/workshop-auth/context/WorkshopAuthContext'
import { slotLabel, todayVn } from '@/features/bookings/utils'
import { getBoard } from '@/features/workshop-board/api'
import type { BoardData } from '@/features/workshop-board/types'

const TODAY_LABEL = new Intl.DateTimeFormat('vi-VN', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' })

/** `/technician` — today's summary from API-WB-01 (first 5 bookings). */
export default function TechnicianDashboard() {
  const navigate = useNavigate()
  const { displayName, workshop } = useWorkshopAuth()
  const [board, setBoard] = useState<BoardData | null>(null)
  const [boardError, setBoardError] = useState<ApiError | null>(null)

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

  const summary = board?.summary
  const stats = [
    { label: 'Chờ xác nhận', value: summary?.PENDING, icon: AlarmClock, tone: 'text-warning bg-warning/10', to: '/technician/board?status=PENDING' },
    { label: 'Lịch hẹn hôm nay', value: board ? board.items.filter(item => item.status !== 'CANCELLED').length : undefined, icon: CalendarClock, tone: 'text-emerald bg-emerald/10', to: '/technician/board' },
    { label: 'Đang làm', value: summary ? summary.CHECKED_IN + summary.IN_PROGRESS : undefined, icon: Wrench, tone: 'text-emerald bg-emerald/10', to: '/technician/board?status=CHECKED_IN&status=IN_PROGRESS' },
  ]

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-8">
        <div>
          <p className="text-xs font-medium text-muted first-letter:uppercase">{TODAY_LABEL.format(new Date())}</p>
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

      <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-6">
        {stats.map(({ label, value, icon: Icon, tone, to }) => (
          <Link key={label} to={to} className="group rounded-2xl p-3 sm:p-5 bg-card border border-border elevation-sm hover:-translate-y-0.5 hover:elevation-md hover:border-emerald/30 transition-all">
            <span className={`hidden sm:flex w-9 h-9 rounded-xl items-center justify-center mb-3 ${tone}`}>
              <Icon className="w-4 h-4" />
            </span>
            <span className="block text-2xl sm:text-3xl font-bold text-foreground font-mono">{value ?? '–'}</span>
            <span className="block text-xs sm:text-sm text-muted mt-1">{label}</span>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5">
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
                    <span className="flex-1 min-w-0">
                      <span className="block text-sm font-medium text-foreground truncate">{item.customer.fullName}</span>
                      <span className="block text-xs text-muted truncate">
                        {item.vehicle.modelName} · {formatLicensePlate(item.vehicle.licensePlate)}
                      </span>
                    </span>
                    {BOOKING_STATUS[item.status] && <Badge tone={BOOKING_STATUS[item.status].tone}>{BOOKING_STATUS[item.status].label}</Badge>}
                    <ChevronRight className="w-4 h-4 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
