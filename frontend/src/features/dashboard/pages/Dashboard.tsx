import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Bot, CalendarClock, ChevronRight, ClipboardList, Sparkles } from 'lucide-react'
import { serviceHistory } from '@/mocks/dashboard'
import StatusBadge from '@/shared/ui/StatusBadge'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { isApiError } from '@/shared/api/client'
import { track } from '@/shared/utils/track'
import { useAuth } from '@/features/auth/context/AuthContext'
import MaintenanceStatusCard from '@/features/vehicles/components/MaintenanceStatusCard'
import { VehicleSummaryCard } from '@/features/vehicles/components/VehicleCards'
import VehicleGate, { VehicleApiError } from '@/features/vehicles/components/VehicleGate'
import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import DiscordConnectBanner from '@/features/notifications/components/DiscordConnectBanner'

const QUICK_ACTIONS = [
  { icon: Bot, label: 'Hỏi AI', sub: 'Tư vấn 24/7', to: '/ai' },
  { icon: CalendarClock, label: 'Đặt lịch', sub: 'Chọn xưởng gần nhất', to: '/booking' },
  { icon: ClipboardList, label: 'Lịch sử dịch vụ', sub: 'Các lần bảo dưỡng', to: '/history' },
]

const SUGGESTED_QUESTIONS = [
  'Mốc bảo dưỡng tới của xe tôi cần làm gì?',
  'Hạng mục nào được bảo hành miễn phí?',
  'Chính sách bảo hành pin thế nào?',
]

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
        <h1 className="text-2xl font-bold text-foreground">Xin chào{displayName ? `, ${displayName}` : ''}</h1>
        <p className="text-muted mt-1">Mọi chuyến đi hôm nay, vì một tương lai xanh hơn.</p>
      </div>

      <DiscordConnectBanner />

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

          <div className="grid grid-cols-3 gap-3 sm:gap-4">
            {QUICK_ACTIONS.map(({ icon: Icon, label, sub, to }) => (
              <Link
                key={label}
                to={to}
                className="bg-card border border-border rounded-2xl p-4 hover:bg-card-hover transition-colors"
              >
                <div className="w-9 h-9 rounded-xl bg-emerald/10 flex items-center justify-center mb-3">
                  <Icon className="w-4 h-4 text-emerald" />
                </div>
                <p className="text-sm font-semibold text-foreground">{label}</p>
                <p className="text-xs text-muted mt-0.5 hidden sm:block">{sub}</p>
              </Link>
            ))}
          </div>

          {/* Service history is not covered by the Sprint 1–2 specs: still mock data. */}
          <div className="bg-card border border-border rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <span className="text-sm font-semibold text-foreground">Lịch sử dịch vụ</span>
              <Link to="/history" className="text-xs text-emerald hover:text-emerald-bright transition-colors font-medium">
                Xem tất cả →
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Mốc km', 'Ngày', 'Hạng mục', 'Xưởng dịch vụ', 'Trạng thái'].map(heading => (
                      <th key={heading} className="px-5 py-3 text-left text-xs font-medium text-muted whitespace-nowrap">
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {serviceHistory.map(row => (
                    <tr key={`${row.km}-${row.date}`} className="border-b border-border last:border-b-0">
                      <td className="px-5 py-3.5 text-foreground font-mono text-xs whitespace-nowrap">{row.km}</td>
                      <td className="px-5 py-3.5 text-muted text-xs font-mono">{row.date}</td>
                      <td className="px-5 py-3.5 text-foreground text-xs">{row.type}</td>
                      <td className="px-5 py-3.5 text-muted text-xs">{row.center}</td>
                      <td className="px-5 py-3.5">
                        <StatusBadge status={row.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <aside className="bg-card border border-border rounded-2xl p-5 h-fit">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="w-9 h-9 rounded-xl bg-emerald/10 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-emerald" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">AI Trợ lý</p>
              <p className="text-xs text-muted">Trả lời theo tài liệu chính hãng</p>
            </div>
          </div>
          <p className="text-sm text-muted leading-relaxed">
            Tra cứu lịch bảo dưỡng, hạng mục, bảo hành và cách dùng xe — kèm nguồn tài liệu chính hãng.
          </p>
          <div className="mt-4 space-y-2">
            {SUGGESTED_QUESTIONS.map(question => (
              <Link
                key={question}
                to={`/ai?q=${encodeURIComponent(question)}`}
                className="flex items-center justify-between gap-3 rounded-xl border border-border px-3.5 py-2.5 text-sm text-foreground hover:bg-card-hover transition-colors"
              >
                {question}
                <ChevronRight className="w-4 h-4 text-muted flex-shrink-0" />
              </Link>
            ))}
          </div>
          <Link
            to="/ai"
            className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm bg-emerald text-background font-semibold hover:bg-emerald-bright transition-colors"
          >
            <Bot className="w-4 h-4" />
            Mở AI Trợ lý
          </Link>
        </aside>
      </div>
    </div>
  )
}
