import { Bell, Bot, CalendarClock, Car, ClipboardList, LayoutDashboard } from 'lucide-react'
import { useAuth } from '@/features/auth/context/AuthContext'
import AppLayout, { type NavItem } from './AppLayout'

const OWNER_NAV: NavItem[] = [
  { to: '/dashboard', label: 'Tổng quan', icon: LayoutDashboard, end: true },
  { to: '/vehicle', label: 'Xe của tôi', icon: Car },
  { to: '/history', label: 'Lịch sử dịch vụ', icon: ClipboardList },
  { to: '/booking', label: 'Đặt lịch', icon: CalendarClock },
  { to: '/ai', label: 'AI Trợ lý', icon: Bot },
  { to: '/notifications', label: 'Thông báo', icon: Bell },
]

/** Owner app shell (guarded by RequireActiveUser). */
export default function OwnerLayout() {
  const { displayName, user, logout } = useAuth()
  return (
    <AppLayout
      nav={OWNER_NAV}
      userName={displayName || 'Chủ xe'}
      roleLabel="Chủ xe"
      avatarUrl={user?.avatarUrl}
      notificationsPath="/notifications"
      onLogout={logout}
    />
  )
}
