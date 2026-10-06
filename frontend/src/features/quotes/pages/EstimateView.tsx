import { useEffect, useState } from 'react'
import { apiGet } from '@/shared/api/client'
import { useVehicleProfile } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

export interface EstimateData {
  chargeableTotal: number
  estimateLabel: string
  milestone: { odoMilestoneKm: number }
  workshop: { workshopId: string; name: string }
  items: { itemCode: string; itemName: string; price: number; covered: boolean }[]
}
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Clock, Wrench, ChevronRight } from 'lucide-react'


const timeline = [
  { label: 'AI Recommendation', done: true },
  { label: 'Cost Estimate', done: true },
  { label: 'Technician Review', done: false, active: true },
  { label: 'Confirmed Quote', done: false },
]

export default function EstimateView({ vehicle }: { vehicle: VehicleSummary }) {
  const navigate = useNavigate()
  const profile = useVehicleProfile(vehicle.userVehicleId)
  const [estimate, setEstimate] = useState<EstimateData | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setEstimate(null); setError('')
    apiGet<EstimateData>(`/user-vehicles/${encodeURIComponent(vehicle.userVehicleId)}/cost-estimate`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setEstimate(value) })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Không tải được dự toán.') })
    return () => controller.abort()
  }, [vehicle.userVehicleId, attempt])
  if (error) return <Card><p role="alert" className="text-error mb-3">{error}</p><Button variant="secondary" onClick={() => setAttempt(n => n + 1)}>Thử lại</Button></Card>
  if (!estimate) return <Card><p role="status" className="text-muted">Đang tải dự toán…</p></Card>
  const services = estimate.items.map(item => ({ name: item.itemName, desc: item.covered ? 'Trong bảo hành' : 'Ngoài bảo hành', price: Number(item.price) }))
  const total = Number(estimate.chargeableTotal)
  const odo = profile.data?.odometer?.odoKm
  const mileage = odo == null ? '—' : `${odo.toLocaleString('vi-VN')} km`
  const bookingUrl = `/booking?workshopId=${encodeURIComponent(estimate.workshop.workshopId)}&odoMilestone=${estimate.milestone.odoMilestoneKm}`

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Ước tính chi phí bảo dưỡng</h1>
        <p className="text-muted text-sm mt-1">{vehicle.modelName ?? 'Xe của bạn'} – {vehicle.licensePlate} • Mileage hiện tại: {mileage}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Main estimate */}
        <div className="lg:col-span-2 space-y-4">
          {/* Timeline */}
          <div
            className="rounded-2xl px-5 py-4"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <div className="flex items-center gap-0">
              {timeline.map((step, i) => (
                <div key={step.label} className="flex items-center flex-1 last:flex-none">
                  <div className="flex flex-col items-center gap-1.5">
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        step.done
                          ? 'bg-emerald text-background'
                          : step.active
                          ? 'bg-warning/20 text-warning ring-1 ring-warning/40'
                          : 'bg-card text-muted'
                      }`}
                      style={!step.done && !step.active ? { border: '1px solid #1F2A28' } : undefined}
                    >
                      {step.done ? <CheckCircle2 className="w-3.5 h-3.5" /> : i + 1}
                    </div>
                    <span className={`text-xs font-medium text-center leading-tight max-w-[80px] ${
                      step.done ? 'text-emerald' : step.active ? 'text-warning' : 'text-muted'
                    }`}>
                      {step.label}
                    </span>
                  </div>
                  {i < timeline.length - 1 && (
                    <div className="flex-1 h-px mx-2 mb-5" style={{ background: step.done ? '#10B981' : '#1F2A28' }} />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Services table */}
          <div
            className="rounded-2xl overflow-hidden"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <div className="px-5 py-4 flex items-center gap-2" style={{ borderBottom: '1px solid #1F2A28' }}>
              <Wrench className="w-4 h-4 text-emerald" />
              <span className="text-sm font-semibold text-foreground">AI Suggested Services</span>
              <span className="ml-auto px-2 py-0.5 rounded-full text-xs text-emerald bg-emerald/10 font-medium">Estimated</span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid #1F2A28' }}>
                  {['Hạng mục', 'Mô tả', 'Estimated Price'].map(h => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-medium text-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {services.map((svc, i) => (
                  <tr
                    key={i}
                    className="hover:bg-card/50 transition-colors"
                    style={i < services.length - 1 ? { borderBottom: '1px solid #1F2A28' } : undefined}
                  >
                    <td className="px-5 py-3.5 text-foreground text-sm font-medium">{svc.name}</td>
                    <td className="px-5 py-3.5 text-muted text-xs">{svc.desc}</td>
                    <td className="px-5 py-3.5 text-foreground font-mono text-sm">
                      {svc.price.toLocaleString('vi-VN')} VND
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div
              className="flex items-center justify-between px-5 py-4"
              style={{ borderTop: '1px solid #1F2A28', background: 'rgba(16,185,129,0.04)' }}
            >
              <span className="text-sm font-semibold text-foreground">Tổng ước tính</span>
              <span className="text-emerald font-bold font-mono text-lg">{total.toLocaleString('vi-VN')} VND</span>
            </div>
          </div>

          {/* Warning */}
          <div
            className="rounded-2xl p-4 flex gap-3"
            style={{ background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.2)' }}
          >
            <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-warning mb-0.5">Chi phí ước tính</p>
              <p className="text-sm text-muted leading-relaxed">
                Đây là chi phí ước tính do AI tính toán. Báo giá chính thức cần được kỹ thuật viên xác nhận.
              </p>
            </div>
          </div>

          {/* Status badge */}
          <div
            className="rounded-2xl px-5 py-4 flex items-center gap-3"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <Clock className="w-4 h-4 text-warning" />
            <div>
              <span className="text-xs font-bold uppercase tracking-widest text-warning font-mono">
                WAITING FOR TECHNICIAN APPROVAL
              </span>
              <p className="text-xs text-muted mt-0.5">Kỹ thuật viên sẽ xem xét và xác nhận báo giá trong 24 giờ làm việc.</p>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div
            className="rounded-2xl p-5"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-4">Thông tin xe</p>
            <div className="space-y-3">
              {[
                ['Model', vehicle.modelName ?? '—'],
                ['Biển số', vehicle.licensePlate],
                ['Mileage', mileage],
                ['Bảo dưỡng kế', `${estimate.milestone.odoMilestoneKm.toLocaleString('vi-VN')} km`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-xs text-muted">{k}</span>
                  <span className="text-xs text-foreground font-medium">{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-2xl p-5 space-y-2.5"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-1">Tiếp theo</p>
            <button
              onClick={() => navigate(bookingUrl)}
              className="w-full py-2.5 rounded-xl text-sm font-semibold bg-emerald text-background hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
            >
              Đặt lịch bảo dưỡng <ChevronRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => navigate('/ai')}
              className="w-full py-2 rounded-xl text-sm font-medium text-muted hover:text-foreground transition-colors"
              style={{ border: '1px solid #1F2A28' }}
            >
              Hỏi thêm AI
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
