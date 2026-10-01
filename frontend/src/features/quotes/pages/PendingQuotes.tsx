import { quotes } from '@/mocks/pending-quotes'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Car } from 'lucide-react'

const statusMap: Record<string, { label: string; cls: string }> = {
  pending: { label: 'PENDING APPROVAL', cls: 'text-warning bg-warning/10' },
  approved: { label: 'APPROVED', cls: 'text-emerald bg-emerald/10' },
  rejected: { label: 'REJECTED', cls: 'text-error bg-error/10' },
}

export default function PendingQuotes() {
  const navigate = useNavigate()

  return (
    <div className="p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Yêu cầu duyệt báo giá</h1>
        <p className="text-muted text-sm mt-1">
          {quotes.filter(q => q.status === 'pending').length} báo giá đang chờ xem xét
        </p>
      </div>

      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: '#171D1C', border: '1px solid #1F2A28' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid #1F2A28' }}>
                {['Xe', 'Khách hàng', 'Mileage', 'Estimated Price', 'Ngày tạo', 'Trạng thái', ''].map(h => (
                  <th key={h} className="px-5 py-3.5 text-left text-xs font-medium text-muted whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {quotes.map((q, i) => {
                const { label, cls } = statusMap[q.status] ?? statusMap.pending
                return (
                  <tr
                    key={i}
                    className="hover:bg-card/60 transition-colors"
                    style={i < quotes.length - 1 ? { borderBottom: '1px solid #1F2A28' } : undefined}
                  >
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-card flex items-center justify-center flex-shrink-0" style={{ border: '1px solid #1F2A28' }}>
                          <Car className="w-3.5 h-3.5 text-muted" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-foreground">{q.vehicle}</div>
                          <div className="text-xs text-muted font-mono">{q.plate}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm text-foreground">{q.customer}</td>
                    <td className="px-5 py-4 text-xs text-muted font-mono whitespace-nowrap">{q.km}</td>
                    <td className="px-5 py-4 text-sm text-foreground font-mono font-semibold whitespace-nowrap">{q.price}</td>
                    <td className="px-5 py-4 text-xs text-muted whitespace-nowrap">{q.created}</td>
                    <td className="px-5 py-4">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold font-mono uppercase tracking-wide ${cls}`}>
                        {label}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      {q.status === 'pending' && (
                        <button
                          onClick={() => navigate('/technician/quote-review')}
                          className="px-3 py-1.5 rounded-xl text-xs font-medium text-emerald flex items-center gap-1 hover:bg-emerald/10 transition-colors whitespace-nowrap"
                          style={{ border: '1px solid rgba(16,185,129,0.2)' }}
                        >
                          Review <ChevronRight className="w-3 h-3" />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
