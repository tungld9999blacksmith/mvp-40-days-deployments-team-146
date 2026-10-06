import { useCallback, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, Settings, XCircle, type LucideIcon } from 'lucide-react'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { formatRelativeDay } from '@/shared/utils/format'
import { addDays, todayVn } from '@/features/bookings/utils'
import { getBoard } from '@/features/workshop-board/api'
import { listNotifications, NOTIFICATION_FEED_KEY } from '../api'
import { portalEntries, toFeedEntry, type FeedEntry, type FeedTone } from '../feed'

const TONE: Record<FeedTone, { icon: LucideIcon; iconColor: string; iconBg: string }> = {
  warning: { icon: AlertTriangle, iconColor: 'text-warning', iconBg: 'bg-warning/10' },
  success: { icon: CheckCircle2, iconColor: 'text-emerald', iconBg: 'bg-emerald/10' },
  error: { icon: XCircle, iconColor: 'text-error', iconBg: 'bg-error/10' },
  info: { icon: Bell, iconColor: 'text-muted', iconBg: 'bg-card border border-border' },
}

/** Owner: API-NOTI-003. Portal: bookings of the next 7 days still waiting for confirmation (API-WB-01). */
function useFeed(variant: 'owner' | 'portal') {
  const fetchOwner = useCallback(async () => {
    const feed = await listNotifications()
    return feed.items.map(toFeedEntry).filter((entry): entry is FeedEntry => entry !== null)
  }, [])
  const fetchPortal = useCallback(async () => {
    const today = todayVn()
    const board = await getBoard({ from: today, to: addDays(today, 6), statuses: ['PENDING'], q: '' })
    return portalEntries(board.items)
  }, [])
  return useCachedQuery(
    variant === 'owner' ? NOTIFICATION_FEED_KEY : 'notifications:portal',
    variant === 'owner' ? fetchOwner : fetchPortal,
    60_000,
  )
}

function FeedCard({ entry }: { entry: FeedEntry }) {
  const navigate = useNavigate()
  const { icon: Icon, iconColor, iconBg } = TONE[entry.tone]
  return (
    <div className={`rounded-2xl p-5 transition-all bg-card border ${entry.unread ? 'border-emerald/15' : 'border-border'}`}>
      <div className="flex gap-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${iconBg}`}>
          <Icon className={`w-4.5 h-4.5 ${iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">{entry.title}</h3>
              {entry.unread && <span className="w-2 h-2 rounded-full bg-emerald flex-shrink-0" aria-label="Mới" />}
            </div>
            {entry.at && <span className="text-xs text-muted flex-shrink-0">{formatRelativeDay(entry.at)}</span>}
          </div>
          <p className="text-sm text-muted mt-1.5 leading-relaxed">{entry.message}</p>
          {entry.action && (
            <button
              onClick={() => navigate(entry.action!.to)}
              className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-emerald hover:text-emerald-bright transition-colors"
            >
              {entry.action.label} <ChevronRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** In-app notifications. No read state exists, so there is no "mark all as read". */
export default function Notifications({ variant }: { variant: 'owner' | 'portal' }) {
  const feed = useFeed(variant)
  const entries = useMemo(() => feed.data ?? [], [feed.data])
  const unreadCount = entries.filter(entry => entry.unread).length

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Thông báo</h1>
          <p className="text-muted text-sm mt-1">
            {variant === 'portal'
              ? 'Lịch hẹn 7 ngày tới đang chờ xưởng xác nhận'
              : unreadCount > 0
                ? `${unreadCount} việc cần bạn xem`
                : 'Hoạt động 90 ngày gần nhất'}
          </p>
        </div>
        {variant === 'owner' && (
          <Link
            to="/notifications/settings"
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm bg-card border border-border text-muted hover:text-foreground hover:bg-card-hover transition-colors"
          >
            <Settings className="w-4 h-4" aria-hidden />
            Cài đặt
          </Link>
        )}
      </div>

      {feed.error && !feed.data ? (
        <ErrorState
          description="Chưa tải được thông báo."
          traceId={feed.error.traceId}
          onRetry={() => void feed.refetch()}
          retrying={feed.isFetching}
        />
      ) : !feed.data ? (
        <div className="space-y-3">
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={<Bell className="w-5 h-5" />}
          title={variant === 'portal' ? 'Không có việc chờ xử lý' : 'Chưa có thông báo'}
          description={
            variant === 'portal'
              ? 'Lịch hẹn mới cần xác nhận sẽ hiện ở đây.'
              : 'Nhắc bảo dưỡng, cập nhật lịch hẹn và khảo sát sau dịch vụ sẽ hiện ở đây.'
          }
        />
      ) : (
        <div className="space-y-3">
          {entries.map(entry => (
            <FeedCard key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}
