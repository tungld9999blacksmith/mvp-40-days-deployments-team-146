import { notifications } from '@/mocks/notifications'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, Settings } from 'lucide-react'

/** In-app notification list — still mock data (no list API yet, US-021 FE Q-FE-NOTI-04). */
export default function Notifications({ showSettings = false }: { showSettings?: boolean }) {
  const navigate = useNavigate()
  const unreadCount = notifications.filter(n => n.unread).length

  return (
    <div className="p-6 xl:p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Thông báo</h1>
          <p className="text-muted text-sm mt-1">
            {unreadCount > 0 ? `${unreadCount} thông báo chưa đọc` : 'Đã đọc tất cả'}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {unreadCount > 0 && (
            <button className="text-xs text-emerald hover:text-emerald-bright transition-colors font-medium">
              Đánh dấu tất cả đã đọc
            </button>
          )}
          {showSettings && (
            <Link
              to="/notifications/settings"
              className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm bg-card border border-border text-muted hover:text-foreground hover:bg-card-hover transition-colors"
            >
              <Settings className="w-4 h-4" aria-hidden />
              Cài đặt
            </Link>
          )}
        </div>
      </div>

      <div className="space-y-3">
        {notifications.map(notif => {
          const Icon = notif.icon
          return (
            <div
              key={notif.id}
              className={`rounded-2xl p-5 transition-all bg-card border ${notif.unread ? 'border-emerald/15' : 'border-border'}`}
            >
              <div className="flex gap-4">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${notif.iconBg} ${
                    notif.type === 'info' ? 'border border-border' : ''
                  }`}
                >
                  <Icon className={`w-4.5 h-4.5 ${notif.iconColor}`} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-foreground">{notif.title}</h3>
                      {notif.unread && (
                        <span className="w-2 h-2 rounded-full bg-emerald flex-shrink-0" />
                      )}
                    </div>
                    <span className="text-xs text-muted flex-shrink-0">{notif.time}</span>
                  </div>

                  <p className="text-sm text-muted mt-1.5 leading-relaxed">{notif.message}</p>

                  {notif.action && (
                    <button
                      onClick={() => navigate(notif.action!.to)}
                      className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-emerald hover:text-emerald-bright transition-colors"
                    >
                      {notif.action.label} <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
