import { useMemo, useState, type KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, ClipboardList, ExternalLink, Search } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import { useMediaQuery, XL_QUERY } from '@/shared/hooks/useMediaQuery'
import Button from '@/shared/ui/Button'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { page } from '@/shared/ui/page'
import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import { useMaintenanceStatus, useServiceRecords } from '@/features/vehicles/hooks/useVehicleQueries'
import type { VehicleSummary } from '@/features/vehicles/types'
import {
  matchesServiceRecord,
  serviceRecordCost,
  serviceRecordSource,
  serviceRecordTitle,
  type ServiceRecordFilter,
} from '../utils'
import HistorySummary from '../components/HistorySummary'
import ServiceRecordDetail from '../components/ServiceRecordDetail'

const FILTERS: { value: ServiceRecordFilter; label: string }[] = [
  { value: 'ALL', label: 'Tất cả' },
  { value: 'PERIODIC', label: 'Bảo dưỡng định kỳ' },
  { value: 'OTHER', label: 'Sửa chữa / kiểm tra' },
]

const PER_PAGE = 10
// Below `sm` only date, item and cost stay as columns: km moves under the date,
// workshop and the booking link under the item. From xl, source and booking link move to the detail rail.
const COLUMNS = [
  { label: 'Ngày', wide: false, railed: false },
  { label: 'Số km', wide: true, railed: false },
  { label: 'Hạng mục', wide: false, railed: false },
  { label: 'Xưởng dịch vụ', wide: true, railed: false },
  { label: 'Nguồn', wide: true, railed: true },
  { label: 'Chi phí', wide: false, railed: false },
  { label: '', wide: true, railed: true },
]

function HistoryTable({ vehicle }: { vehicle: VehicleSummary }) {
  const navigate = useNavigate()
  const records = useServiceRecords(vehicle.userVehicleId)
  const status = useMaintenanceStatus(vehicle.userVehicleId)
  // xl: table in 2/3, the chosen record in full on the right (DESIGN.md 2026-10-11).
  const wide = useMediaQuery(XL_QUERY)
  const [chosen, setChosen] = useState<string | null>(null)
  const [filter, setFilter] = useState<ServiceRecordFilter>('ALL')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const filtered = useMemo(
    () => (records.data?.items ?? []).filter(record => matchesServiceRecord(record, filter, search)),
    [records.data, filter, search],
  )
  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE))
  const rows = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE)
  const selected = wide ? (rows.find(record => record.recordId === chosen) ?? rows[0] ?? null) : null

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
        action={<Button onClick={() => navigate('/booking')}>Đặt lịch bảo dưỡng</Button>}
      />
    )
  }

  return (
    <>
      <HistorySummary records={records.data.items} status={status.data} />
      <div className="xl:grid xl:grid-cols-3 xl:gap-6 xl:items-start">
        <div className="xl:col-span-2 min-w-0">
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
            className="pl-9 pr-4 py-2 rounded-xl text-sm text-foreground bg-card focus-field transition-all w-64"
            style={{ border: '1px solid var(--color-border)' }}
          />
        </div>
      </div>

      <div className="rounded-2xl overflow-hidden elevation-sm" style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {COLUMNS.map(({ label, wide: hiddenOnPhone, railed }, index) => (
                  <th
                    key={index}
                    className={cn(
                      'px-3 sm:px-5 py-3.5 text-left text-xs font-medium text-muted whitespace-nowrap',
                      hiddenOnPhone && 'hidden sm:table-cell',
                      railed && 'xl:hidden',
                    )}
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
                  const isSelected = record.recordId === selected?.recordId
                  return (
                    <tr
                      key={record.recordId}
                      className={cn(
                        'hover:bg-card/60 transition-colors',
                        wide && 'cursor-pointer hover:bg-card-hover focus-visible:bg-card-hover',
                        isSelected && 'bg-emerald-dim hover:bg-emerald-dim shadow-[inset_3px_0_0_var(--color-emerald)]',
                      )}
                      style={index < rows.length - 1 ? { borderBottom: '1px solid var(--color-border)' } : undefined}
                      {...(wide
                        ? {
                            tabIndex: 0,
                            'aria-selected': isSelected,
                            onClick: () => setChosen(record.recordId),
                            onKeyDown: (event: KeyboardEvent) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                setChosen(record.recordId)
                              }
                            },
                          }
                        : {})}
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
                      <td className="hidden sm:table-cell xl:hidden px-5 py-3.5 text-muted text-xs whitespace-nowrap">{serviceRecordSource(record)}</td>
                      <td className="px-3 sm:px-5 py-3.5 text-foreground font-mono text-xs whitespace-nowrap">
                        {cost !== null ? formatVnd(cost) : '—'}
                      </td>
                      <td className="hidden sm:table-cell xl:hidden px-5 py-3.5">
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
        </div>
        {selected && <ServiceRecordDetail record={selected} className="xl:sticky xl:top-6 xl:mt-[60px]" />}
      </div>
    </>
  )
}

/** Service history (API-VEH-005): manufacturer records + EV Care visits, read-only (BR-003). */
export default function ServiceHistory() {
  return (
    <div className={page()}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Lịch sử dịch vụ</h1>
        <p className="text-muted text-sm mt-1">Các lần bảo dưỡng và sửa chữa của xe, đồng bộ từ hãng và từ EV Care</p>
      </div>
      <VehicleGate loading={<SkeletonCard lines={5} />}>{vehicle => <HistoryTable vehicle={vehicle} />}</VehicleGate>
    </div>
  )
}
