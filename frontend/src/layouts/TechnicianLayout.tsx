import { Bell, CalendarDays, FileText, Gauge, LayoutDashboard, QrCode, Settings2, Tags, Users } from 'lucide-react'
import { useWorkshopAuth } from '@/features/workshop-auth/context/WorkshopAuthContext'
import AppLayout, { type NavItem } from './AppLayout'

/** Workshop Portal shell (guarded by RequireActiveWorkshopOwner). */
export default function TechnicianLayout() {
  const { displayName, owner, workshop, logout } = useWorkshopAuth()
  const nav: NavItem[] = [
    { to: '/technician', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/technician/board', label: 'Lịch hẹn', icon: CalendarDays },
    { to: '/technician/quotes', label: 'Báo giá', icon: FileText },
    { to: '/technician/check-in', label: 'Check-in', icon: QrCode },
    { to: '/technician/capacity', label: 'Sức chứa', icon: Gauge },
    { to: '/technician/price-list', label: 'Bảng giá', icon: Tags },
    { to: '/technician/settings/booking', label: 'Cài đặt đặt lịch', icon: Settings2 },
    { to: '/technician/notifications', label: 'Thông báo', icon: Bell },
    { to: '/customers', label: 'Khách hàng', icon: Users, disabled: true },
  ]
  return (
    <AppLayout
      nav={nav}
      userName={displayName || 'Chủ xưởng'}
      roleLabel={workshop ? `Chủ xưởng · ${workshop.name}` : 'Chủ xưởng'}
      avatarUrl={owner?.avatarUrl}
      notificationsPath="/technician/notifications"
      brandSuffix="Workshop"
      onLogout={logout}
      logoutTitle="Đăng xuất khỏi Workshop Portal?"
      logoutDescription="Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục quản lý xưởng."
      logoutNote="Nếu Gmail này cũng dùng ứng dụng EV Care dành cho chủ xe, bạn có thể phải đăng nhập lại ứng dụng đó."
    />
  )
}
