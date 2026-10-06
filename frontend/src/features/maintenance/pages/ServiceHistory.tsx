import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, ClipboardList, ExternalLink, Search } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import { useServiceRecords } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import {
  matchesServiceRecord,
  serviceRecordCost,
  serviceRecordSource,
  serviceRecordTitle,
  type ServiceRecordFilter,
} from '../utils'

const FILTERS: { value: ServiceRecordFilter; label: string }[] = [
  { value: 'ALL', label: 'Tất cả' },
  { value: 'PERIODIC', label: 'Bảo dưỡng định kỳ' },
  { value: 'OTHER', label: 'Sửa chữa / kiểm tra' },
]

const PER_PAGE = 10
// Below `sm` only date, item and cost stay as columns: km moves under the date,
// workshop and the booking link under the item.
const COLUMNS = [
  { label: 'Ngày', wide: false },
  { label: 'Số km', wide: true },
  { label: 'Hạng mục', wide: false },
  { label: 'Xưởng dịch vụ', wide: true },
  { label: 'Nguồn', wide: true },
  { label: 'Chi phí', wide: false },
  { label: '', wide: true },
]

function HistoryTable({ vehicle }: { vehicle: VehicleSummary }) {
  const records = useServiceRecords(vehicle.userVehicleId)
  const [filter, setFilter] = useState<ServiceRecordFilter>('ALL')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const filtered = useMemo(
    () => (records.data?.items ?? []).filter(record => matchesServiceRecord(record, filter, search)),
    [records.data, filter, search],
  )
  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE))
  const rows = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE)

  if (records.error && !records.data) {
    return (
      <ErrorState
        description="Chưa tải được lịch sử dịch vụ."
        traceId={isApiError(records.error) ? records.error.traceId : null}
        onRetry={() => void records.refetch()}
        retrying={records.isFetching}
      />
    )
  }
  if (!records.data) return <SkeletonCard lines={5} />
  if (records.data.items.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList className="w-5 h-5" />}
        title="Chưa có lịch sử dịch vụ"
        description="Các lần bảo dưỡng từ hãng và lịch hẹn hoàn thành trên EV Care sẽ hiện ở đây."
      />
    )
  }

  return (
    <>
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-5">
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map(item => (
            <button
              key={item.value}
              onClick={() => {
                setFilter(item.value)
                setPage(1)
              }}
              className={`px-3.5 py-1.5 rounded-xl text-sm font-medium transition-all ${
                filter === item.value ? 'bg-emerald text-background' : 'text-muted hover:text-foreground'
              }`}
              style={filter !== item.value ? { background: 'var(--color-card)', border: '1px solid var(--color-border)' } : undefined}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="relative sm:ml-auto">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <input
            value={search}
            onChange={event => {
              setSearch(event.target.value)
              setPage(1)
            }}
            placeholder="Tìm hạng mục, xưởng, mã lịch hẹn..."
            className="pl-9 pr-4 py-2 rounded-xl text-sm text-foreground bg-card focus:outline-none focus:ring-1 focus:ring-emerald/40 transition-all w-64"
            style={{ border: '1px solid var(--color-border)' }}
          />
        </div>
      </div>

      <div className="rounded-2xl overflow-hidden elevation-sm" style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {COLUMNS.map(({ label, wide }, index) => (
                  <th
                    key={index}
                    className={cn('px-3 sm:px-5 py-3.5 text-left text-xs font-medium text-muted whitespace-nowrap', wide && 'hidden sm:table-cell')}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="px-5 py-10 text-center text-muted text-sm">
                    Không tìm thấy kết quả phù hợp
                  </td>
                </tr>
              ) : (
                rows.map((record, index) => {
                  const cost = serviceRecordCost(record)
                  return (
                    <tr
                      key={record.recordId}
                      className="hover:bg-card/60 transition-colors"
                      style={index < rows.length - 1 ? { borderBottom: '1px solid var(--color-border)' } : undefined}
                    >
                      <td className="px-3 sm:px-5 py-3.5 text-foreground text-xs whitespace-nowrap">
                        {formatDate(record.serviceDate)}
                        {record.odoKm !== null && (
                          <span className="sm:hidden block mt-0.5 text-muted font-mono">{formatKm(record.odoKm)}</span>
                        )}
                      </td>
                      <td className="hidden sm:table-cell px-5 py-3.5 text-muted font-mono text-xs whitespace-nowrap">
                        {record.odoKm !== null ? formatKm(record.odoKm) : '—'}
                      </td>
                      <td className="px-3 sm:px-5 py-3.5 text-foreground text-xs">
                        {serviceRecordTitle(record)}
                        {record.workshop && <span className="sm:hidden block mt-0.5 text-muted">{record.workshop.name}</span>}
                        {record.bookingId && (
                          <Link
                            to={`/bookings/${encodeURIComponent(record.bookingId)}`}
                            className="sm:hidden mt-1 inline-flex items-center gap-1 text-emerald"
                          >
                            Lịch hẹn <ExternalLink className="w-3 h-3" />
                          </Link>
                        )}
                      </td>
                      <td className="hidden sm:table-cell px-5 py-3.5 text-muted text-xs whitespace-nowrap">{record.workshop?.name ?? '—'}</td>
                      <td className="hidden sm:table-cell px-5 py-3.5 text-muted text-xs whitespace-nowrap">{serviceRecordSource(record)}</td>
                      <td className="px-3 sm:px-5 py-3.5 text-foreground font-mono text-xs whitespace-nowrap">
                        {cost !== null ? formatVnd(cost) : '—'}
                      </td>
                      <td className="hidden sm:table-cell px-5 py-3.5">
                        {record.bookingId && (
                          <Link
                            to={`/bookings/${encodeURIComponent(record.bookingId)}`}
                            className="text-xs text-emerald hover:text-emerald-bright flex items-center gap-1 transition-colors"
                          >
                            Lịch hẹn <ExternalLink className="w-3 h-3" />
                          </Link>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-5 py-3.5" style={{ borderTop: '1px solid var(--color-border)' }}>
          <span className="text-xs text-muted">
            Hiển thị {filtered.length === 0 ? 0 : (page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, filtered.length)} trong{' '}
            {filtered.length} kết quả
          </span>
          <div className="flex gap-1.5">
            <button
              onClick={() => setPage(current => Math.max(1, current - 1))}
              disabled={page === 1}
              aria-label="Trang trước"
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              style={{ border: '1px solid var(--color-border)' }}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, index) => (
              <button
                key={index}
                onClick={() => setPage(index + 1)}
                className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-all ${
                  page === index + 1 ? 'bg-emerald text-background' : 'text-muted hover:text-foreground hover:bg-card'
                }`}
                style={page !== index + 1 ? { border: '1px solid var(--color-border)' } : undefined}
              >
                {index + 1}
              </button>
            ))}
            <button
              onClick={() => setPage(current => Math.min(totalPages, current + 1))}
              disabled={page === totalPages}
              aria-label="Trang sau"
              className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              style={{ border: '1px solid var(--color-border)' }}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

/** Service history (API-VEH-005): manufacturer records + EV Care visits, read-only (BR-003). */
export default function ServiceHistory() {
  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Lịch sử dịch vụ</h1>
        <p className="text-muted text-sm mt-1">Các lần bảo dưỡng và sửa chữa của xe, đồng bộ từ hãng và từ EV Care</p>
      </div>
      <VehicleGate loading={<SkeletonCard lines={5} />}>{vehicle => <HistoryTable vehicle={vehicle} />}</VehicleGate>
    </div>
  )
}
