import { useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronRight,
  Settings,
  XCircle,
  type LucideIcon,
} from "lucide-react"
import { SkeletonCard } from "@/shared/ui/Skeleton"
import { EmptyState, ErrorState, Notice } from "@/shared/ui/States"
import { cn } from "@/shared/ui/cn"
import { page } from "@/shared/ui/page"
import { formatRelativeDay } from "@/shared/utils/format"
import { useNotificationFeed } from "../hooks/useNotificationFeed"
import {
  attentionEntries,
  groupFeedEntries,
  type FeedEntry,
  type FeedTone,
} from "../feed"
import {
  NotificationSettingsSummary,
  NotificationTasks,
} from "../components/NotificationRail"

const TONE: Record<FeedTone, {
  icon: LucideIcon
  iconColor: string
  iconBg: string
}> = {
  warning: {
    icon: AlertTriangle,
    iconColor: "text-warning",
    iconBg: "bg-warning/10",
  },
  success: {
    icon: CheckCircle2,
    iconColor: "text-emerald",
    iconBg: "bg-emerald/10",
  },
  error: { icon: XCircle, iconColor: "text-error", iconBg: "bg-error/10" },
  info: {
    icon: Bell,
    iconColor: "text-muted",
    iconBg: "bg-card border border-border",
  },
}

function FeedCard({ entry }: { entry: FeedEntry }) {
  const navigate = useNavigate()
  const { icon: Icon, iconColor, iconBg } = TONE[entry.tone]
  return (
    <div
      className={`rounded-2xl p-5 transition-all bg-card border ${
        entry.unread ? "border-emerald/15" : "border-border"
      }`}
    >
      <div className="flex gap-4">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${iconBg}`}
        >
          <Icon className={`w-4.5 h-4.5 ${iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <h2 className="text-sm font-semibold text-foreground">
                {entry.title}
              </h2>
              {entry.unread && (
                <span
                  className="w-2 h-2 rounded-full bg-emerald flex-shrink-0"
                  aria-label="Mới"
                />
              )}
            </div>
            {entry.at && (
              <span className="text-xs text-muted flex-shrink-0">
                {formatRelativeDay(entry.at)}
              </span>
            )}
          </div>
          <p className="text-sm text-muted mt-1.5 leading-relaxed">
            {entry.message}
          </p>
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
export default function Notifications({
  variant,
}: {
  variant: "owner" | "portal"
}) {
  const feed = useNotificationFeed(variant)
  const entries = useMemo(() => feed.data ?? [], [feed.data])
  const taskCount = attentionEntries(entries).length
  const groups = useMemo(() => groupFeedEntries(entries), [entries])

  return (
    <div
      className={cn(
        page(variant === "owner" ? "full" : "reading"),
        variant === "owner" && "max-w-[1600px]",
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Thông báo</h1>
          <p className="text-muted text-sm mt-1">
            {variant === "portal"
              ? "Báo giá chờ duyệt và lịch hẹn 7 ngày tới đang chờ xưởng xác nhận"
              : taskCount > 0 && !feed.error
                ? `${taskCount} việc cần bạn xem`
                : "Hoạt động 90 ngày gần nhất"}
          </p>
        </div>
        {variant === "owner" && (
          <Link
            to="/notifications/settings"
            className="inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm bg-card border border-border text-muted hover:text-foreground hover:bg-card-hover transition-colors"
          >
            <Settings className="w-4 h-4" aria-hidden />
            Cài đặt
          </Link>
        )}
      </div>

      {feed.error && feed.data && (
        <Notice tone="warning" className="mb-4">
          Chưa cập nhật được thông báo. Đang hiển thị lần tải trước.
        </Notice>
      )}
      <div
        className={
          variant === "owner"
            ? "grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start"
            : ""
        }
      >
        <section className="min-w-0" aria-label="Danh sách thông báo">
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
              title={
                variant === "portal"
                  ? "Không có việc chờ xử lý"
                  : "Chưa có thông báo"
              }
              description={
                variant === "portal"
                  ? "Báo giá mới và lịch hẹn cần xác nhận sẽ hiện ở đây."
                  : "Nhắc bảo dưỡng, kết quả báo giá, cập nhật lịch hẹn và khảo sát sau dịch vụ sẽ hiện ở đây."
              }
            />
          ) : (
            <div className="space-y-6">
              {(variant === "owner" ? groups : [{ label: "", entries }]).map(
                (group) => (
                  <div key={group.label}>
                    {group.label && (
                      <p className="mb-3 text-xs font-semibold text-muted">
                        {group.label}
                      </p>
                    )}
                    <div className="space-y-3">
                      {group.entries.map((entry) => (
                        <FeedCard key={entry.id} entry={entry} />
                      ))}
                    </div>
                  </div>
                ),
              )}
            </div>
          )}
        </section>
        {variant === "owner" && (
          <aside
            className="space-y-5 min-w-0"
            aria-label="Tóm tắt và cài đặt thông báo"
          >
            <NotificationTasks
              entries={entries}
              loading={!feed.data && !feed.error}
              error={feed.error}
              onRetry={() => void feed.refetch()}
              retrying={feed.isFetching}
            />
            <NotificationSettingsSummary />
          </aside>
        )}
      </div>
    </div>
  )
}
