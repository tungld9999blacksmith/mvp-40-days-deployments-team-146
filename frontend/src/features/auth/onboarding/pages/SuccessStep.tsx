import { useEffect } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { InfoRow } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { vehicleDisplayName, warrantyComponentLabel } from '@/shared/domain/labels'
import { formatDate, formatKm, formatLicensePlate } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { useAuth } from '../../context/AuthContext'
import { resolveOnboardingRoute } from '../../navigation'
import { useOnboarding } from '../OnboardingContext'

/** SCR-005 — onboarding completed (US-001 FE §4.5). */
export default function SuccessStep() {
  const navigate = useNavigate()
  const { onboarding } = useAuth()
  const { outcome, snapshot, loadSnapshot } = useOnboarding()
  const active = onboarding?.status === 'ACTIVE'

  // The API-005 result is only usable when it is the VERIFIED one (not a stale PENDING).
  const verified = outcome?.result?.status === 'VERIFIED' ? outcome : null
  const vehicle = verified?.vehicle ?? snapshot?.vehicle ?? null
  const warranties = verified ? verified.warranties : snapshot?.warranties ?? []

  useEffect(() => {
    if (active) track('onboarding_completed')
  }, [active])

  useEffect(() => {
    if (active && !verified && snapshot?.onboarding.status !== 'ACTIVE') void loadSnapshot()
  }, [active, verified, snapshot, loadSnapshot])

  if (!onboarding) return null
  if (!active) return <Navigate to={resolveOnboardingRoute(onboarding)} replace />
  if (!vehicle) return <SkeletonCard lines={5} />

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-14 h-14 rounded-2xl bg-emerald/10 flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7 text-emerald" aria-hidden />
        </div>
        <h1 className="text-2xl font-bold text-foreground mt-5">Xác thực xe thành công</h1>
        <p className="text-sm text-muted mt-1">Tài khoản của bạn đã sẵn sàng.</p>
      </div>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Xe của bạn</p>
        <InfoRow label="Mẫu xe" value={vehicleDisplayName(vehicle.spec?.modelName, vehicle.spec?.trim)} />
        <InfoRow label="Biển số" value={formatLicensePlate(vehicle.licensePlate)} mono />
        <InfoRow label="Số VIN" value={vehicle.vin} mono />
      </section>

      <section className="bg-card border border-border rounded-2xl p-5 sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-2">Bảo hành</p>
        {warranties.length === 0 ? (
          <p className="text-sm text-muted py-2">Chưa có thông tin bảo hành từ hãng.</p>
        ) : (
          <ul className="divide-y divide-border">
            {warranties.map(warranty => (
              <li key={warranty.component} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{warrantyComponentLabel(warranty.component)}</p>
                  <p className="text-xs text-muted mt-0.5 font-mono">
                    Đến {formatDate(warranty.endDate)}
                    {warranty.kmLimit ? ` · ${formatKm(warranty.kmLimit)}` : ''}
                  </p>
                </div>
                <Badge tone={warranty.status === 'ACTIVE' ? 'success' : 'neutral'}>
                  {warranty.status === 'ACTIVE' ? 'Còn hiệu lực' : 'Hết hiệu lực'}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Button size="lg" fullWidth onClick={() => navigate('/dashboard', { replace: true })}>
        Vào trang chủ
      </Button>
    </div>
  )
}
