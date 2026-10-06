import { Link } from 'react-router-dom'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { cn } from '@/shared/ui/cn'
import { formatDate, formatKm } from '@/shared/utils/format'
import { serviceRecordSource, serviceRecordTitle } from '@/features/maintenance/utils'
import { useServiceRecords, useVehicles } from '@/features/vehicles/hooks/useVehicleQueries'

const RECENT = 3
// Workshop and source columns drop below `sm`; the workshop moves under the item instead.
const COLUMNS = [
  { label: 'Số km', wide: false },
  { label: 'Ngày', wide: false },
  { label: 'Hạng mục', wide: false },
  { label: 'Xưởng dịch vụ', wide: true },
  { label: 'Nguồn', wide: true },
]

/** Home: the three latest service records (API-VEH-005). Vehicle errors are shown by the card above. */
export default function RecentServiceHistory() {
  const vehicles = useVehicles()
  const vehicle = vehicles.data?.[0] ?? null
  const records = useServiceRecords(vehicle?.userVehicleId ?? null)

  if (!vehicle) return null
  if (!records.data) return records.error ? null : <SkeletonCard lines={3} />

  const rows = records.data.items.slice(0, RECENT)
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden elevation-sm">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <span className="text-sm font-semibold text-foreground">Lịch sử dịch vụ</span>
        <Link to="/history" className="text-xs text-emerald hover:text-emerald-bright transition-colors font-medium">
          Xem tất cả →
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted">Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {COLUMNS.map(({ label, wide }) => (
                  <th
                    key={label}
                    className={cn('px-3 sm:px-5 py-3 text-left text-xs font-medium text-muted whitespace-nowrap', wide && 'hidden sm:table-cell')}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(record => (
                <tr key={record.recordId} className="border-b border-border last:border-b-0">
                  <td className="px-3 sm:px-5 py-3.5 text-foreground font-mono text-xs whitespace-nowrap">
                    {record.odoKm !== null ? formatKm(record.odoKm) : '—'}
                  </td>
                  <td className="px-3 sm:px-5 py-3.5 text-muted text-xs font-mono whitespace-nowrap">{formatDate(record.serviceDate)}</td>
                  <td className="px-3 sm:px-5 py-3.5 text-foreground text-xs">
                    {serviceRecordTitle(record)}
                    {record.workshop && <span className="sm:hidden block mt-0.5 text-muted">{record.workshop.name}</span>}
                  </td>
                  <td className="hidden sm:table-cell px-5 py-3.5 text-muted text-xs">{record.workshop?.name ?? '—'}</td>
                  <td className="hidden sm:table-cell px-5 py-3.5 text-muted text-xs">{serviceRecordSource(record)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
