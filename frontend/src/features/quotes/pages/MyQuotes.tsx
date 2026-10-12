import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronRight, FileText } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { page } from '@/shared/ui/page'
import { formatDate, formatKm } from '@/shared/utils/format'
import { formatVnd } from '@/features/estimate/utils'
import { listMyQuotes } from '../api'
import QuoteStatusBadge from '../components/QuoteStatusBadge'
import type { QuoteListItem } from '../types'
import { hasUnseenResult } from '../utils'

/** SCR-1103 — Báo giá của tôi (`/quotes`, `?unseenResult=true` from the Home badge). */
export default function MyQuotes() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const unseenOnly = searchParams.get('unseenResult') === 'true'
  const [items, setItems] = useState<QuoteListItem[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(
    async (from: string | null) => {
      setError(null)
      try {
        const page = await listMyQuotes({ unseenResult: unseenOnly, cursor: from })
        setItems(previous => (from && previous ? [...previous, ...page.items] : page.items))
        setCursor(page.nextCursor)
      } catch (reason) {
        setError(isApiError(reason) ? reason : null)
      }
    },
    [unseenOnly],
  )

  useEffect(() => {
    setItems(null)
    void load(null)
  }, [load])

  return (
    <div className={page('reading')}>
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Báo giá của tôi</h1>
          <p className="text-muted mt-1">Báo giá có xưởng xác nhận, dùng được khi đặt lịch.</p>
        </div>
        <Button variant="secondary" icon={<FileText className="w-4 h-4" />} onClick={() => navigate('/estimate')}>
          Xem chi phí dự kiến
        </Button>
      </div>

      <div className="flex gap-2 mb-4" role="tablist" aria-label="Lọc báo giá">
        {[
          { key: false, label: 'Tất cả' },
          { key: true, label: 'Có kết quả mới' },
        ].map(tab => (
          <button
            key={tab.label}
            role="tab"
            aria-selected={unseenOnly === tab.key}
            onClick={() => setSearchParams(tab.key ? { unseenResult: 'true' } : {})}
            className={cn(
              'px-3.5 py-1.5 rounded-full text-sm font-medium border transition-colors',
              unseenOnly === tab.key ? 'bg-emerald/10 text-emerald border-emerald/30' : 'text-muted border-border hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {items === null && !error ? (
        <div className="space-y-3" aria-busy>
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      ) : error && !items ? (
        <Card>
          <ErrorState traceId={error.traceId} onRetry={() => void load(null)} />
        </Card>
      ) : items && items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FileText className="w-5 h-5" />}
            title={unseenOnly ? 'Chưa có báo giá nào có kết quả mới.' : 'Bạn chưa có báo giá nào.'}
            description={unseenOnly ? undefined : 'Xem chi phí dự kiến để bắt đầu.'}
            action={!unseenOnly ? <Button onClick={() => navigate('/estimate')}>Xem chi phí dự kiến</Button> : undefined}
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {items?.map(quote => (
            <li key={quote.quoteId}>
              <Link
                to={`/quotes/${encodeURIComponent(quote.quoteId)}`}
                className="group flex items-center gap-4 bg-card border border-border rounded-2xl p-4 elevation-sm hover:border-emerald/30 hover:-translate-y-0.5 hover:elevation-md transition-all"
              >
                <span className="w-10 h-10 rounded-xl bg-emerald/10 text-emerald flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4" />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground truncate">{quote.workshop.name}</span>
                    {hasUnseenResult(quote) && <span className="w-2 h-2 rounded-full bg-emerald" aria-label="Kết quả mới" />}
                  </span>
                  <span className="block text-xs text-muted mt-0.5">
                    Mốc {formatKm(quote.odoMilestone)} · lập {formatDate(quote.createdAt)}
                  </span>
                </span>
                <span className="text-right shrink-0">
                  <QuoteStatusBadge status={quote.displayStatus} />
                  <span className="block font-mono text-sm text-foreground mt-1.5">{formatVnd(quote.approvedTotal ?? quote.estimatedTotal)}</span>
                </span>
                <ChevronRight className="w-4 h-4 text-muted shrink-0 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </li>
          ))}
        </ul>
      )}

      {cursor && (
        <div className="flex justify-center mt-4">
          <Button
            variant="secondary"
            loading={loadingMore}
            onClick={async () => {
              setLoadingMore(true)
              await load(cursor)
              setLoadingMore(false)
            }}
          >
            Xem thêm
          </Button>
        </div>
      )}
    </div>
  )
}
