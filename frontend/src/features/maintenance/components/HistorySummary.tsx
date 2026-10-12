import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { cn } from '@/shared/ui/cn'
import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import type { MaintenanceStatus, ServiceRecord } from '@/features/vehicles/types'
import { remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import { serviceHistorySummary } from '../utils'

function Cell({ index, label, value, sub }: { index: number; label: string; value: ReactNode; sub: ReactNode }) {
  return (
    <div
      className={cn(
        'px-4 sm:px-5 py-4 min-w-0 border-border',
        index % 2 === 1 && 'border-l',
        index >= 2 && 'border-t lg:border-t-0',
        index === 2 && 'lg:border-l',
      )}
    >
      <p className="text-xs text-muted">{label}</p>
      <p className="font-mono text-xl font-bold text-foreground mt-0.5 truncate">{value}</p>
      <p className="text-xs text-muted mt-0.5 truncate">{sub}</p>
    </div>
  )
}

/** "06/2025" from an ISO day. */
function monthYear(day: string): string {
  const [year, month] = day.split('-')
  return `${month}/${year}`
}

/** Strip above the history table: periodic visits, the latest one, EV Care spend, next milestone. */
export default function HistorySummary({ records, status }: { records: ServiceRecord[]; status: MaintenanceStatus | null | undefined }) {
  const summary = serviceHistorySummary(records)
  const { latest, evCareCost } = summary
  const next = status?.nextMilestone ?? null
  const remaining = status && next ? remainingParts(status)[0] : undefined

  return (
    <Card className="p-0 grid grid-cols-2 lg:grid-cols-4 mb-5">
      <Cell
        index={0}
        label="Bảo dưỡng định kỳ"
        value={`${summary.periodicCount} lần`}
        sub={summary.firstPeriodicDate ? `từ ${monthYear(summary.firstPeriodicDate)}` : 'Chưa có lần nào'}
      />
      <Cell
        index={1}
        label="Lần gần nhất"
        value={latest ? formatDate(latest.serviceDate) : '—'}
        sub={latest ? [latest.odoKm !== null ? formatKm(latest.odoKm) : null, latest.workshop?.name].filter(Boolean).join(' · ') || '—' : '—'}
      />
      <Cell
        index={2}
        label="Chi phí qua EV Care"
        value={evCareCost.count > 0 ? formatVnd(evCareCost.total) : '—'}
        sub={evCareCost.count > 0 ? `${evCareCost.count} lần có chi phí` : 'Chưa có lần nào qua EV Care'}
      />
      <Cell
        index={3}
        label="Mốc tiếp theo"
        value={next ? formatKm(next.odoMilestoneKm) : '—'}
        sub={
          next ? (
            <>
              {remaining && <span className={cn(remaining.emphasized && 'text-warning font-semibold')}>{remaining.text}</span>}
              {remaining && ' · '}
              <Link to={`/booking?odoMilestone=${next.odoMilestoneKm}`} className="text-emerald font-medium hover:text-emerald-bright">
                Đặt lịch
              </Link>
            </>
          ) : (
            'Chưa xác định'
          )
        }
      />
    </Card>
  )
}
