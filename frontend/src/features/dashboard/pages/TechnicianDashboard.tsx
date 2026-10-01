import { pendingQuotes, todayAppointments } from '@/mocks/technician-dashboard'
import { useNavigate } from 'react-router-dom'
import { FileText, CalendarClock, CheckCircle2, AlertTriangle, ChevronRight, TrendingUp } from 'lucide-react'

const stats = [
  { label: 'Pending Quotes', value: '3', sub: 'Chờ duyệt báo giá', icon: FileText, color: 'text-warning', bg: 'bg-warning/10', to: '/technician/quotes' },
  { label: "Today's Appointments", value: '5', sub: 'Lịch hẹn hôm nay', icon: CalendarClock, color: 'text-emerald', bg: 'bg-emerald/10', to: '/notifications' },
  { label: 'Completed Services', value: '28', sub: 'Tháng này', icon: CheckCircle2, color: 'text-emerald', bg: 'bg-emerald/10', to: '/notifications' },
  { label: 'Overdue Vehicles', value: '2', sub: 'Cần liên hệ ngay', icon: AlertTriangle, color: 'text-error', bg: 'bg-error/10', to: '/notifications' },
]

export default function TechnicianDashboard() {
  const navigate = useNavigate()

  return (
    <div className="p-6 xl:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Dashboard Kỹ thuật viên</h1>
        <p className="text-muted text-sm mt-1">Trần Minh Kỹ • Thứ Tư, 17/09/2026</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats.map(({ label, value, sub, icon: Icon, color, bg, to }) => (
          <button
            key={label}
            onClick={() => navigate(to)}
            className="rounded-2xl p-5 text-left transition-all hover:brightness-110 hover:scale-[1.02] active:scale-100"
            style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
          >
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 ${bg}`}>
              <Icon className={`w-4.5 h-4.5 ${color}`} />
            </div>
            <div className="text-3xl font-bold text-foreground font-mono">{value}</div>
            <div className="text-sm font-semibold text-foreground mt-1">{label}</div>
            <div className="text-xs text-muted mt-0.5">{sub}</div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Pending quotes */}
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
        >
          <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid #1F2A28' }}>
            <span className="text-sm font-semibold text-foreground">Báo giá chờ duyệt</span>
            <button
              onClick={() => navigate('/technician/quotes')}
              className="text-xs text-emerald hover:text-emerald-bright transition-colors"
            >
              Xem tất cả →
            </button>
          </div>
          <div className="divide-y" style={{ borderColor: '#1F2A28' }}>
            {pendingQuotes.map((q, i) => (
              <div key={i} className="px-5 py-4 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-foreground">{q.vehicle}</div>
                  <div className="text-xs text-muted font-mono mt-0.5">{q.plate} • {q.customer}</div>
                  <div className="flex items-center gap-3 mt-1.5">
                    <span className="text-xs text-muted">{q.km}</span>
                    <span className="text-xs text-foreground font-mono font-medium">{q.price}</span>
                  </div>
                </div>
                <button
                  onClick={() => navigate('/technician/quote-review')}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium text-emerald flex items-center gap-1 hover:bg-emerald/10 transition-colors flex-shrink-0"
                  style={{ border: '1px solid rgba(16,185,129,0.2)' }}
                >
                  Review <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Today's appointments */}
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
        >
          <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid #1F2A28' }}>
            <span className="text-sm font-semibold text-foreground">Lịch hẹn hôm nay</span>
            <span className="text-xs text-muted">{todayAppointments.length} lịch hẹn</span>
          </div>
          <div className="divide-y" style={{ borderColor: '#1F2A28' }}>
            {todayAppointments.map((appt, i) => (
              <div key={i} className="px-5 py-4 flex items-start gap-4">
                <div
                  className="text-sm font-bold text-foreground font-mono flex-shrink-0 w-12 mt-0.5"
                >
                  {appt.time}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground">{appt.vehicle}</div>
                  <div className="text-xs text-muted mt-0.5">{appt.customer}</div>
                  <div className="text-xs text-muted mt-0.5">{appt.type}</div>
                </div>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-semibold flex-shrink-0 ${
                    appt.status === 'completed'
                      ? 'text-emerald bg-emerald/10'
                      : 'text-muted bg-card'
                  }`}
                  style={appt.status !== 'completed' ? { border: '1px solid #1F2A28' } : undefined}
                >
                  {appt.status === 'completed' ? 'Hoàn thành' : 'Sắp tới'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
