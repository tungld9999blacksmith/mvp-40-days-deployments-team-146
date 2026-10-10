import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Clock, FileText, MessagesSquare } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import { Card } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { formatKm, formatLicensePlate, formatTimeDayMonth } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import { listWorkshopQuotes } from '../api'
import QuoteStatusBadge from '../components/QuoteStatusBadge'
import type { WorkshopQuoteItem, WorkshopQuoteList } from '../types'

type Tab = 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
const TABS: { key: Tab; label: string }[] = [
  { key: 'PENDING_APPROVAL', label: 'Chờ duyệt' },
  { key: 'APPROVED', label: 'Đã duyệt' },
  { key: 'REJECTED', label: 'Bị từ chối' },
]

function waiting(hours: number): string {
  if (hours < 1) return 'Dưới 1 giờ'
  if (hours < 24) return `${hours} giờ`
  return `${Math.floor(hours / 24)} ngày ${hours % 24} giờ`
}

/** SCR-1111 — quotes of the workshop (API-QT-11); waiting longest first. */
export default function PendingQuotes() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (TABS.find(item => item.key === searchParams.get('status'))?.key ?? 'PENDING_APPROVAL') as Tab
  const [data, setData] = useState<WorkshopQuoteList | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(() => {
    setError(null)
    setData(null)
    listWorkshopQuotes(tab)
      .then(setData)
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }, [tab])

  useEffect(load, [load])

  const open = (item: WorkshopQuoteItem) => navigate(`/technician/quote-review?quoteId=${encodeURIComponent(item.quoteId)}`)

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Báo giá</h1>
        <p className="text-muted mt-1">Duyệt, điều chỉnh giá hoặc từ chối báo giá khách gửi tới xưởng.</p>
      </div>

      <div className="flex flex-wrap gap-2 mb-4" role="tablist" aria-label="Trạng thái báo giá">
        {TABS.map(item => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => setSearchParams(item.key === 'PENDING_APPROVAL' ? {} : { status: item.key })}
            className={cn(
              'px-3.5 py-1.5 rounded-full text-sm font-medium border transition-colors inline-flex items-center gap-2',
              tab === item.key ? 'bg-emerald/10 text-emerald border-emerald/30' : 'text-muted border-border hover:text-foreground',
            )}
          >
            {item.label}
            {data?.summary && (
              <span className="text-xs font-mono opacity-80">{data.summary[item.key]}</span>
            )}
          </button>
        ))}
      </div>

      <Card className="p-0 overflow-hidden">
        {error ? (
          <ErrorState traceId={error.traceId} onRetry={load} />
        ) : !data ? (
          <div className="p-5 space-y-3" aria-busy>
            {[0, 1, 2].map(index => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <EmptyState icon={<FileText className="w-5 h-5" />} title={tab === 'PENDING_APPROVAL' ? 'Không có báo giá chờ duyệt.' : 'Chưa có báo giá nào.'} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted">
                  <th className="px-5 py-3 font-medium">Khách</th>
                  <th className="px-5 py-3 font-medium">Xe</th>
                  <th className="px-5 py-3 font-medium">Mốc</th>
                  <th className="px-5 py-3 font-medium text-right">{tab === 'APPROVED' ? 'Tổng duyệt' : 'Tổng ước tính'}</th>
                  <th className="px-5 py-3 font-medium">Gửi lúc</th>
                  <th className="px-5 py-3 font-medium">{tab === 'PENDING_APPROVAL' ? 'Đã chờ' : 'Xử lý sau'}</th>
                  <th className="px-5 py-3 font-medium">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(item => (
                  <tr
                    key={item.quoteId}
                    tabIndex={0}
                    onClick={() => open(item)}
                    onKeyDown={event => event.key === 'Enter' && open(item)}
                    className="border-b border-border last:border-0 cursor-pointer hover:bg-card-hover focus:bg-card-hover focus:outline-none"
                  >
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-foreground">{item.customer.fullName}</span>
                      {item.hasConversation && <MessagesSquare className="inline w-3.5 h-3.5 ml-1.5 text-muted" aria-label="Có hội thoại" />}
                    </td>
                    <td className="px-5 py-3.5 text-muted whitespace-nowrap">
                      {item.modelName} · <span className="font-mono">{formatLicensePlate(item.plateNumber)}</span>
                    </td>
                    <td className="px-5 py-3.5 text-muted whitespace-nowrap">{formatKm(item.odoMilestone)}</td>
                    <td className="px-5 py-3.5 text-right font-mono text-foreground whitespace-nowrap">
                      {formatVnd(tab === 'APPROVED' && item.approvedTotal !== null ? item.approvedTotal : item.estimatedTotal)}
                    </td>
                    <td className="px-5 py-3.5 text-muted whitespace-nowrap">{item.submittedAt ? formatTimeDayMonth(item.submittedAt) : '—'}</td>
                    <td className="px-5 py-3.5 whitespace-nowrap">
                      {item.isWaitingLong ? (
                        <Badge tone="error" icon={<Clock className="w-3.5 h-3.5" />}>
                          Chờ &gt; 24h
                        </Badge>
                      ) : (
                        <span className="text-muted">{waiting(item.waitingHours)}</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <QuoteStatusBadge status={item.displayStatus} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
