import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Bot, CalendarClock, ChevronRight, ClipboardList, Sparkles } from 'lucide-react'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { isApiError } from '@/shared/api/client'
import { track } from '@/shared/utils/track'
import { useAuth } from '@/features/auth/context/AuthContext'
import MaintenanceStatusCard from '@/features/vehicles/components/MaintenanceStatusCard'
import { VehicleSummaryCard } from '@/features/vehicles/components/VehicleCards'
import VehicleGate, { VehicleApiError } from '@/features/vehicles/components/VehicleGate'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import HomeCarousel from '../components/HomeCarousel'
import HomeHighlights from '../components/HomeHighlights'
import RecentServiceHistory from '../components/RecentServiceHistory'

const QUICK_ACTIONS = [
  { icon: Bot, label: 'Hỏi AI', sub: 'Tư vấn 24/7', to: '/ai' },
  { icon: CalendarClock, label: 'Đặt lịch', sub: 'Chọn xưởng gần nhất', to: '/booking' },
  { icon: ClipboardList, label: 'Lịch sử dịch vụ', sub: 'Các lần bảo dưỡng', to: '/history' },
]

const TODAY_LABEL = new Intl.DateTimeFormat('vi-VN', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  timeZone: 'Asia/Ho_Chi_Minh',
})

const SUGGESTED_QUESTIONS = [
  'Mốc bảo dưỡng tới của xe tôi cần làm gì?',
  'Hạng mục nào được bảo hành miễn phí?',
  'Chính sách bảo hành pin thế nào?',
]

/** Shortcuts: under the vehicle cards up to lg, a column under the AI card on xl. */
function QuickActions({ className }: { className?: string }) {
  return (
    <div className={cn('grid grid-cols-3 xl:grid-cols-1 gap-3 sm:gap-4', className)}>
      {QUICK_ACTIONS.map(({ icon: Icon, label, sub, to }) => (
        <Link
          key={label}
          to={to}
          className="group relative flex flex-col sm:flex-row sm:items-center gap-3 bg-card border border-border rounded-2xl p-4 elevation-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-emerald/40 hover:elevation-md"
        >
          <div className="w-10 h-10 rounded-xl bg-emerald-dim flex items-center justify-center shrink-0">
            <Icon className="w-4 h-4 text-emerald" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">{label}</p>
            <p className="text-xs text-muted mt-0.5 hidden sm:block">{sub}</p>
          </div>
          <ChevronRight className="absolute top-4 right-4 w-4 h-4 text-muted opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0 hidden xl:block" />
        </Link>
      ))}
    </div>
  )
}

function VehicleOverview({ vehicle }: { vehicle: VehicleSummary }) {
  const status = useMaintenanceStatus(vehicle.userVehicleId)

  useEffect(() => {
    if (status.data) {
      track('maintenance_status_viewed', {
        dueStatus: status.data.dueStatus,
        dueReason: status.data.dueReason,
        calculationBasis: status.data.calculationBasis,
        screen: 'home',
      })
    }
  }, [status.data])

  const vehicleError =
    status.error && ['VEHICLE_NOT_FOUND', 'VEHICLE_NOT_ACTIVE', 'ONBOARDING_REQUIRED'].some(code => isApiError(status.error, code))

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <VehicleSummaryCard vehicle={vehicle} />
      {vehicleError && status.error ? (
        <VehicleApiError error={status.error} onRetry={() => void status.refetch()} title="Không tải được trạng thái bảo dưỡng." />
      ) : (
        <MaintenanceStatusCard
          variant="compact"
          status={status.data}
          error={status.error}
          onRetry={() => void status.refetch()}
          retrying={status.isFetching && status.data !== null}
          pendingSyncExhausted={status.pendingSyncExhausted}
          onRetryPendingSync={status.retryPendingSync}
        />
      )}
    </div>
  )
}

/** SCR-301 — Home: due status first (wireframe §18), then shortcuts. */
export default function Dashboard() {
  const { displayName } = useAuth()

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="mb-8">
        <p className="text-xs font-medium text-muted first-letter:uppercase">{TODAY_LABEL.format(new Date())}</p>
        <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Xin chào{displayName ? ', ' : ''}
          {displayName && <span>{displayName}</span>}
        </h1>
      </div>

      <HomeCarousel />

      <HomeHighlights />


      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 space-y-6">
          <VehicleGate
            loading={
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <SkeletonCard lines={4} />
                <SkeletonCard lines={4} />
              </div>
            }
          >
            {vehicle => <VehicleOverview vehicle={vehicle} />}
          </VehicleGate>

          <QuickActions className="xl:hidden" />

          <RecentServiceHistory />
        </div>

        <div className="space-y-6">
          <aside className="relative overflow-hidden bg-card border border-border rounded-2xl p-5 h-fit elevation-sm">
            <div className="relative flex items-center gap-2.5 mb-4">
              <div className="w-10 h-10 rounded-xl bg-brand flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-on-brand" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">AI Trợ lý</p>
                <p className="text-xs text-muted">Trả lời theo tài liệu chính hãng</p>
              </div>
            </div>
            <p className="relative text-sm text-muted leading-relaxed">
              Tra cứu lịch bảo dưỡng, hạng mục, bảo hành và cách dùng xe — kèm nguồn tài liệu chính hãng.
            </p>
            <div className="relative mt-4 space-y-2">
              {SUGGESTED_QUESTIONS.map(question => (
                <Link
                  key={question}
                  to={`/ai?q=${encodeURIComponent(question)}`}
                  className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-background/40 px-3.5 py-2.5 text-sm text-foreground hover:border-emerald/30 hover:bg-emerald/5 transition-colors"
                >
                  {question}
                  <ChevronRight className="w-4 h-4 text-muted flex-shrink-0 transition-transform group-hover:translate-x-0.5 group-hover:text-emerald" />
                </Link>
              ))}
            </div>
            <Link
              to="/ai"
              className="relative mt-4 w-full inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm bg-brand-gradient text-on-brand font-semibold glow-emerald hover:brightness-110 transition-all active:scale-[0.98]"
            >
              <Bot className="w-4 h-4" />
              Mở AI Trợ lý
            </Link>
          </aside>
          <QuickActions className="hidden xl:grid" />
        </div>
      </div>
    </div>
  )
}
