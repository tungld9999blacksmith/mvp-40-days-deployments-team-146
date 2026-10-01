import { useEffect } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { CheckCircle2, MapPin } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { InfoRow } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { track } from '@/shared/utils/track'
import { useWorkshopAuth } from '../../context/WorkshopAuthContext'
import { resolveWorkshopRoute } from '../../navigation'
import { DAY_LABELS, normalizeOperatingHours } from '../../operatingHours'
import { useWorkshopOnboarding } from '../WorkshopOnboardingContext'

const TYPE_LABEL: Record<string, string> = { DEALER: 'Đại lý 3S', SERVICE_ONLY: 'Xưởng dịch vụ' }

/** SCR-205 — workshop confirmed by the manufacturer (US-009 FE §4.5). */
export default function WorkshopSuccessStep() {
  const navigate = useNavigate()
  const { onboarding, workshop: sessionWorkshop } = useWorkshopAuth()
  const { outcome, snapshot, loadSnapshot } = useWorkshopOnboarding()
  const active = onboarding?.status === 'ACTIVE'
  const workshop = outcome?.workshop ?? snapshot?.workshop ?? sessionWorkshop

  useEffect(() => {
    if (active && workshop) track('workshop_onboarding_completed', { centerId: workshop.centerId })
  }, [active, workshop])

  useEffect(() => {
    if (active && !workshop) void loadSnapshot()
  }, [active, workshop, loadSnapshot])

  if (!onboarding) return null
  if (!active) return <Navigate to={resolveWorkshopRoute(onboarding)} replace />
  if (!workshop) return <SkeletonCard lines={6} />

  const hours = normalizeOperatingHours(workshop.operatingHours)

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-14 h-14 rounded-2xl bg-emerald/10 flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7 text-emerald" aria-hidden />
        </div>
        <h1 className="text-2xl font-bold text-foreground mt-5">Xác thực chủ xưởng thành công</h1>
        <p className="text-sm text-muted mt-1">Xưởng của bạn đã sẵn sàng nhận lịch hẹn.</p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted">Xưởng do hãng xác nhận</p>
            <h2 className="text-lg font-semibold text-foreground mt-2">{workshop.name}</h2>
            <p className="text-sm text-muted mt-0.5 font-mono">{workshop.centerId}</p>
          </div>
          <Badge tone={workshop.status === 'ACTIVE' ? 'success' : 'neutral'}>{workshop.status === 'ACTIVE' ? 'Hoạt động' : workshop.status}</Badge>
        </div>
        <div className="mt-4">
          <InfoRow label="Khu vực" value={workshop.region} />
          <InfoRow label="Loại xưởng" value={TYPE_LABEL[workshop.type] ?? workshop.type} />
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="bg-card border border-border rounded-2xl p-5 sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Vận hành</p>
          <InfoRow label="Địa chỉ" value={workshop.address} />
          <InfoRow label="Hotline" value={workshop.hotline ?? '—'} mono />
          <InfoRow label="Kỹ thuật viên mỗi ca" value={workshop.totalTechnicians} mono />
          <InfoRow label="Slot dự phòng" value={workshop.emergencySlotsReserved} mono />
          {workshop.latitude === null && (
            <p className="flex items-center gap-1.5 text-xs text-muted mt-3">
              <MapPin className="w-3.5 h-3.5" aria-hidden />
              Chưa có vị trí trên bản đồ.
            </p>
          )}
        </section>
        <section className="bg-card border border-border rounded-2xl p-5 sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Giờ hoạt động</p>
          <ul>
            {hours.map((hour, index) => (
              <li key={hour.dayOfWeek} className="flex justify-between py-2 border-b border-border last:border-b-0 text-sm">
                <span className="text-muted">{DAY_LABELS[index]}</span>
                <span className="font-mono text-foreground">
                  {hour.isClosed ? <span className="text-muted font-sans">Đóng cửa</span> : `${hour.openTime} – ${hour.closeTime}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <Button size="lg" fullWidth onClick={() => navigate('/technician', { replace: true })}>
        Vào Dashboard
      </Button>
    </div>
  )
}
