import { Link } from "react-router-dom"
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  MessageSquare,
  Settings,
  type LucideIcon,
} from "lucide-react"
import type { ApiError } from "@/shared/api/client"
import { cn } from "@/shared/ui/cn"
import Skeleton from "@/shared/ui/Skeleton"
import { ErrorState, Notice } from "@/shared/ui/States"
import { attentionEntries, type FeedAttention, type FeedEntry } from "../feed"
import { useNotificationSettings } from "../hooks/useNotificationSettings"

const ICONS: Record<FeedAttention["category"], LucideIcon> = {
  maintenance: AlertTriangle,
  decision: ClipboardList,
  appointment: CalendarClock,
  quote: ClipboardList,
  survey: MessageSquare,
}

export function NotificationTasks({
  entries,
  loading,
  error,
  onRetry,
  retrying,
}: {
  entries: FeedEntry[]
  loading: boolean
  error: ApiError | null
  onRetry: () => void
  retrying: boolean
}) {
  const tasks = attentionEntries(entries)
  return (
    <section
      className="rounded-2xl border border-border bg-card p-5"
      aria-labelledby="notification-tasks-title"
    >
      <div className="flex items-center justify-between gap-3">
        <h2
          id="notification-tasks-title"
          className="text-base font-semibold tracking-tight text-foreground"
        >
          Việc cần xử lý
        </h2>
        {!loading && !error && tasks.length > 0 && (
          <span
            className="min-w-5 h-5 px-1.5 rounded-full bg-brand text-on-brand text-[11px] font-bold inline-flex items-center justify-center"
            aria-label={`${tasks.length} việc cần xử lý`}
          >
            {tasks.length}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Ưu tiên những việc cần bạn phản hồi.
      </p>
      {error ? (
        <ErrorState
          compact
          title="Chưa tải được việc cần xử lý."
          traceId={error.traceId}
          onRetry={onRetry}
          retrying={retrying}
        />
      ) : loading ? (
        <div
          className="mt-5 space-y-4"
          aria-busy="true"
          aria-label="Đang tải việc cần xử lý"
        >
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="mt-5 flex items-start gap-2.5 rounded-xl bg-emerald-dim p-3">
          <CheckCircle2
            className="mt-0.5 w-4 h-4 shrink-0 text-emerald"
            aria-hidden
          />
          <p className="text-sm text-foreground">
            Bạn đã xử lý hết các việc cần chú ý.
          </p>
        </div>
      ) : (
        <>
          <ul className="mt-4 divide-y divide-border border-t border-border">
            {tasks.slice(0, 3).map((entry, index) => {
              const task = entry.attention
              const Icon = ICONS[task.category]
              return (
                <li key={entry.id} className="py-4 last:pb-0">
                  <div
                    className={cn(
                      "flex items-center gap-1.5 text-[11px] font-semibold",
                      task.priority <= 1 ? "text-warning" : "text-muted",
                    )}
                  >
                    <Icon className="w-3.5 h-3.5 shrink-0" aria-hidden />
                    {task.label}
                  </div>
                  <h3 className="mt-1.5 text-sm font-semibold text-foreground break-words">
                    {task.title}
                  </h3>
                  <p className="mt-1 text-xs leading-relaxed text-muted break-words">
                    {task.description}
                  </p>
                  <Link
                    to={entry.action.to}
                    aria-label={`${entry.action.label}: ${task.title}`}
                    className={cn(
                      "mt-3 inline-flex items-center gap-1.5 rounded-xl text-xs font-semibold transition-colors",
                      index === 0
                        ? "w-full justify-center bg-brand text-on-brand px-3 py-2.5 hover:brightness-110"
                        : "text-emerald hover:text-emerald-bright",
                    )}
                  >
                    {entry.action.label}
                    <ChevronRight
                      className="w-3.5 h-3.5 shrink-0"
                      aria-hidden
                    />
                  </Link>
                </li>
              )
            })}
          </ul>
          {tasks.length > 3 && (
            <p className="mt-4 border-t border-border pt-3 text-xs text-muted">
              Còn {tasks.length - 3} việc cần chú ý trong danh sách thông báo.
            </p>
          )}
        </>
      )}
    </section>
  )
}

export function NotificationSettingsSummary() {
  const settings = useNotificationSettings()
  return (
    <section
      className="rounded-2xl border border-border bg-card p-5"
      aria-labelledby="notification-settings-title"
    >
      <div className="flex items-center justify-between gap-3">
        <h2
          id="notification-settings-title"
          className="text-base font-semibold tracking-tight text-foreground"
        >
          Nhắc bảo dưỡng
        </h2>
        <Settings className="w-4 h-4 text-muted" aria-hidden />
      </div>
      {!settings.data && settings.error ? (
        <ErrorState
          compact
          title="Chưa tải được cài đặt nhắc."
          traceId={settings.error.traceId}
          onRetry={() => void settings.refetch()}
          retrying={settings.isFetching}
        />
      ) : !settings.data ? (
        <div
          className="mt-5 space-y-4"
          aria-busy="true"
          aria-label="Đang tải cài đặt nhắc"
        >
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      ) : (
        <>
          {settings.error && (
            <Notice tone="warning" className="mt-4">
              Chưa cập nhật được cài đặt. Đang hiển thị lần tải trước.
            </Notice>
          )}
          <dl className="mt-4 space-y-3 text-xs">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Trạng thái</dt>
              <dd
                className={cn(
                  "rounded-full px-2.5 py-0.5 font-semibold",
                  settings.data.remindersEnabled
                    ? "bg-emerald-dim text-emerald"
                    : "bg-card-hover text-muted",
                )}
              >
                {settings.data.remindersEnabled ? "Đang bật" : "Đang tắt"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Nhắc trước</dt>
              <dd className="font-semibold text-foreground">
                {settings.data.reminderLeadDays} ngày
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Áp dụng cho</dt>
              <dd className="font-semibold text-foreground">Tất cả xe</dd>
            </div>
          </dl>
        </>
      )}
      <div className="mt-5 border-t border-border pt-4">
        <Link
          to="/notifications/settings"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald hover:text-emerald-bright transition-colors"
        >
          Điều chỉnh cài đặt
          <ChevronRight className="w-3.5 h-3.5" aria-hidden />
        </Link>
      </div>
    </section>
  )
}
