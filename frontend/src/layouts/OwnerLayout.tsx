import { Bell, Bot, Calculator, CalendarPlus, Car, ClipboardList, FileText, LayoutDashboard, Ticket } from 'lucide-react'
import DemoAccountBanner from '@/features/auth/components/DemoAccountBanner'
import { useAuth } from '@/features/auth/context/AuthContext'
import { useUnseenQuotes } from '@/features/quotes/hooks'
import { legacyQuotesAllowed, usePricingFlow } from '@/features/booking-lines/flow'
import CurrentVehicleChip from '@/features/vehicles/currentVehicle/CurrentVehicleChip'
import { SUPPORT_PATH } from '@/features/support/logic'
import { useNotificationFeed } from '@/features/notifications/hooks/useNotificationFeed'
import { attentionEntries } from '@/features/notifications/feed'
import AppLayout, { type NavItem } from './AppLayout'

/** Owner app shell (guarded by RequireActiveUser). */
export default function OwnerLayout() {
  const { displayName, user, logout } = useAuth()
  const unseenQuotes = useUnseenQuotes().data?.items.length ?? 0
  const notifications = useNotificationFeed('owner', true)
  const notificationCount = attentionEntries(notifications.data ?? []).length
  // two_tier creates no quotes; old ones stay reachable from their booking (design review D1 = A).
  const quotesInNav = legacyQuotesAllowed(usePricingFlow())
  const nav: NavItem[] = [
    { to: '/dashboard', label: 'Tổng quan', icon: LayoutDashboard, end: true },
    { to: '/vehicle', label: 'Xe của tôi', icon: Car },
    // Labels match the page titles; two near-identical calendar icons side by side were easy to confuse.
    { to: '/bookings', label: 'Lịch hẹn của tôi', icon: Ticket },
    { to: '/booking', label: 'Đặt lịch bảo dưỡng', icon: CalendarPlus },
    { to: '/estimate', label: 'Chi phí bảo dưỡng', icon: Calculator },
    ...(quotesInNav ? [{ to: '/quotes', label: 'Báo giá', icon: FileText, badge: unseenQuotes }] : []),
    { to: '/ai', label: 'AI Trợ lý', icon: Bot },
    { to: '/history', label: 'Lịch sử dịch vụ', icon: ClipboardList },
    { to: '/notifications', label: 'Thông báo', icon: Bell, badge: notificationCount, badgeLabel: `${notificationCount} việc cần xử lý` },
  ]
  return (
    <AppLayout
      nav={nav}
      userName={displayName || 'Chủ xe'}
      roleLabel="Chủ xe"
      avatarUrl={user?.avatarUrl}
      notificationsPath="/notifications"
      supportPath={SUPPORT_PATH}
      headerExtra={<CurrentVehicleChip />}
      notice={user?.isDemo ? <DemoAccountBanner resetsAt={user.demoResetsAt} /> : undefined}
      onLogout={logout}
    />
  )
}
