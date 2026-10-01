import { allRecords } from '@/mocks/service-history'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'

const filters = ['Tất cả', 'Bảo dưỡng', 'Sửa chữa', 'Kiểm tra']

const statusMap: Record<string, { label: string; cls: string }> = {
  completed: { label: 'Hoàn thành', cls: 'text-emerald bg-emerald/10' },
  pending: { label: 'Chờ xử lý', cls: 'text-muted bg-card' },
}

export default function ServiceHistory() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('Tất cả')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const perPage = 5

  const filtered = allRecords.filter(r => {
    const matchFilter = filter === 'Tất cả' || r.type.toLowerCase().includes(filter.toLowerCase())
    const matchSearch = search === '' || r.type.toLowerCase().includes(search.toLowerCase()) || r.center.toLowerCase().includes(search.toLowerCase())
    return matchFilter && matchSearch
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage))
  const rows = filtered.slice((page - 1) * perPage, page * perPage)

  return (
    <div className="p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Lịch sử dịch vụ</h1>
        <p className="text-muted text-sm mt-1">Tất cả các lần bảo dưỡng và sửa chữa của xe</p>
      </div>

      {/* Filter + Search */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-5">
        <div className="flex gap-1.5 flex-wrap">
          {filters.map(f => (
            <button
              key={f}
              onClick={() => { setFilter(f); setPage(1) }}
              className={`px-3.5 py-1.5 rounded-xl text-sm font-medium transition-all ${
                filter === f
                  ? 'bg-emerald text-background'
                  : 'text-muted hover:text-foreground'
              }`}
              style={filter !== f ? { background: '#171D1C', border: '1px solid #1F2A28' } : undefined}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="relative sm:ml-auto">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="Tìm hạng mục, xưởng..."
            className="pl-9 pr-4 py-2 rounded-xl text-sm text-foreground bg-card focus:outline-none focus:ring-1 focus:ring-emerald/40 transition-all w-64"
            style={{ border: '1px solid #1F2A28' }}
          />
        </div>
      </div>

      {/* Table */}
      <div className="rounded-2xl overflow-hidden" style={{ background: '#171D1C', border: '1px solid #1F2A28' }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid #1F2A28' }}>
                {['Ngày', 'Mileage', 'Hạng mục', 'Service Center', 'Kỹ thuật viên', 'Chi phí', 'Trạng thái', ''].map(h => (
                  <th key={h} className="px-5 py-3.5 text-left text-xs font-medium text-muted whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-muted text-sm">
                    Không tìm thấy kết quả phù hợp
                  </td>
                </tr>
              ) : rows.map((row, i) => {
                const { label, cls } = statusMap[row.status] ?? statusMap.pending
                return (
                  <tr
                    key={i}
                    className="hover:bg-card/60 transition-colors"
                    style={i < rows.length - 1 ? { borderBottom: '1px solid #1F2A28' } : undefined}
                  >
                    <td className="px-5 py-3.5 text-foreground text-xs whitespace-nowrap">{row.date}</td>
                    <td className="px-5 py-3.5 text-muted font-mono text-xs whitespace-nowrap">{row.km} km</td>
                    <td className="px-5 py-3.5 text-foreground text-xs">{row.type}</td>
                    <td className="px-5 py-3.5 text-muted text-xs whitespace-nowrap">{row.center}</td>
                    <td className="px-5 py-3.5 text-muted text-xs whitespace-nowrap">{row.technician}</td>
                    <td className="px-5 py-3.5 text-foreground font-mono text-xs whitespace-nowrap">{row.cost}</td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>{label}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <button className="text-xs text-emerald hover:text-emerald-bright flex items-center gap-1 transition-colors">
                        Chi tiết <ExternalLink className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-5 py-3.5" style={{ borderTop: '1px solid #1F2A28' }}>
          <span className="text-xs text-muted">
            Hiển thị {Math.min((page - 1) * perPage + 1, filtered.length)}–{Math.min(page * perPage, filtered.length)} trong {filtered.length} kết quả
          </span>
          <div className="flex gap-1.5">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              style={{ border: '1px solid #1F2A28' }}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => (
              <button
                key={i}
                onClick={() => setPage(i + 1)}
                className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-all ${
                  page === i + 1 ? 'bg-emerald text-background' : 'text-muted hover:text-foreground hover:bg-card'
                }`}
                style={page !== i + 1 ? { border: '1px solid #1F2A28' } : undefined}
              >
                {i + 1}
              </button>
            ))}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              style={{ border: '1px solid #1F2A28' }}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
