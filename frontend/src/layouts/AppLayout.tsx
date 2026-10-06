import { useEffect, useState, type ComponentType } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, LogOut, Menu, WifiOff, X } from 'lucide-react'
import LogoutConfirmDialog from '@/features/auth/components/LogoutConfirmDialog'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'
import { cn } from '@/shared/ui/cn'
import { ICON_BUTTON } from '@/shared/ui/iconButton'
import Logo from '@/shared/ui/Logo'
import SupportLink from '@/shared/ui/SupportLink'
import ThemeToggle from '@/shared/ui/ThemeToggle'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
  /** Not built yet: shown greyed with "Sắp có". */
  disabled?: boolean
  /** Count shown as a pill (e.g. unread notifications); hidden when 0. */
  badge?: number
}

interface AppLayoutProps {
  nav: NavItem[]
  userName: string
  roleLabel: string
  avatarUrl?: string | null
  notificationsPath: string
  brandSuffix?: string
  onLogout: () => Promise<unknown>
  logoutTitle?: string
  logoutDescription?: string
  logoutNote?: string
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return parts.slice(-2).map(part => part[0]?.toUpperCase() ?? '').join('') || 'EV'
}

function Sidebar({ nav, brandSuffix, onLogoutClick, onNavigate }: {
  nav: NavItem[]
  brandSuffix?: string
  onLogoutClick: () => void
  onNavigate?: () => void
}) {
  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="h-16 flex items-center gap-2.5 px-5">
        {/* At h-9 the wordmark plus the suffix badge overflow the 240px sidebar. */}
        <Logo className={cn('text-sidebar-foreground', brandSuffix ? 'h-7' : 'h-9')} />
        {brandSuffix && (
          <span className="shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold text-emerald bg-emerald/10 ring-1 ring-inset ring-emerald/20">
            {brandSuffix}
          </span>
        )}
      </div>

      <p className="px-6 pt-4 pb-2 text-xs font-semibold text-sidebar-muted">Menu</p>
      <nav className="flex-1 px-3 pb-4 space-y-1 overflow-y-auto" aria-label="Điều hướng chính">
        {nav.map(({ to, label, icon: Icon, end, disabled, badge }) =>
          disabled ? (
            <span
              key={to}
              aria-disabled="true"
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-sidebar-muted/50 cursor-not-allowed"
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
              <span className="ml-auto text-[11px] font-medium">Sắp có</span>
            </span>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  'relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'bg-sidebar-active text-sidebar-foreground font-semibold [&>svg]:text-sidebar-active-foreground'
                    : 'text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-hover',
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
              {badge ? (
                <span className="ml-auto min-w-5 h-5 px-1.5 rounded-full bg-brand text-on-brand text-[11px] font-bold flex items-center justify-center" aria-label={`${badge} mới`}>
                  {badge > 99 ? '99+' : badge}
                </span>
              ) : null}
            </NavLink>
          ),
        )}
      </nav>

      <div className="mx-3 mb-4 pt-3 space-y-1 border-t border-sidebar-border">
        <SupportLink label="Hỗ trợ" variant="sidebar" />
        <button
          type="button"
          onClick={onLogoutClick}
          className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium text-sidebar-muted hover:text-error hover:bg-error/10 w-full transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Đăng xuất
        </button>
      </div>
    </div>
  )
}

/** App shell: fixed sidebar (desktop), drawer (mobile), topbar, offline banner, logout confirm. */
export default function AppLayout({
  nav,
  userName,
  roleLabel,
  avatarUrl,
  notificationsPath,
  brandSuffix,
  onLogout,
  logoutTitle,
  logoutDescription,
  logoutNote,
}: AppLayoutProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const online = useOnlineStatus()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)

  useEffect(() => setDrawerOpen(false), [location.pathname])

  // Longest matching entry: `/technician/board/…` is "Lịch hẹn", not the `/technician` dashboard.
  const current = nav
    .filter(item => !item.disabled && (location.pathname === item.to || (!item.end && location.pathname.startsWith(`${item.to}/`))))
    .sort((a, b) => b.to.length - a.to.length)[0]

  const openLogout = () => {
    setDrawerOpen(false)
    setLogoutOpen(true)
  }

  return (
    <div className="flex h-screen bg-background bg-app-backdrop overflow-hidden">
      <aside className="hidden lg:block w-60 flex-shrink-0 border-r border-sidebar-border">
        <Sidebar nav={nav} brandSuffix={brandSuffix} onLogoutClick={openLogout} />
      </aside>

      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" aria-hidden onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 border-r border-sidebar-border bg-sidebar elevation-md">
            <Sidebar
              nav={nav}
              brandSuffix={brandSuffix}
              onLogoutClick={openLogout}
              onNavigate={() => setDrawerOpen(false)}
            />
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              aria-label="Đóng menu"
              className="absolute top-4 -right-12 w-9 h-9 rounded-full bg-surface border border-border flex items-center justify-center text-muted"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-16 bg-surface/60 backdrop-blur-xl border-b border-border flex items-center px-4 sm:px-6 gap-3 flex-shrink-0">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Mở menu"
            className={cn(ICON_BUTTON, 'lg:hidden')}
          >
            <Menu className="w-4 h-4" />
          </button>
          <Logo className="hidden sm:block lg:hidden h-6 text-foreground" />
          {current && <p className="text-base font-semibold text-foreground truncate">{current.label}</p>}

          <div className="flex items-center gap-2 sm:gap-3 ml-auto">
            <ThemeToggle />
            <button type="button" onClick={() => navigate(notificationsPath)} aria-label="Thông báo" className={ICON_BUTTON}>
              <Bell className="w-4 h-4" />
            </button>
            <span aria-hidden className="hidden sm:block w-px h-6 bg-border mx-1" />
            <div className="flex items-center gap-2.5 select-none rounded-full sm:border sm:border-border sm:bg-card/60 sm:pl-1 sm:pr-4 sm:py-1">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" referrerPolicy="no-referrer" className="w-8 h-8 rounded-full object-cover ring-2 ring-emerald/30" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-brand-gradient flex items-center justify-center flex-shrink-0">
                  <span className="text-on-brand text-xs font-bold">{initialsOf(userName)}</span>
                </div>
              )}
              <div className="hidden sm:block min-w-0">
                <div className="text-sm font-semibold text-foreground leading-tight truncate max-w-[180px]">{userName}</div>
                <div className="text-[11px] text-muted leading-tight truncate max-w-[180px]">{roleLabel}</div>
              </div>
            </div>
          </div>
        </header>

        {!online && (
          <div role="status" className="flex items-center gap-2 px-4 sm:px-6 py-2 bg-warning/10 border-b border-warning/20 text-xs text-warning">
            <WifiOff className="w-3.5 h-3.5" aria-hidden />
            Mất kết nối mạng. Một số tính năng tạm thời không dùng được.
          </div>
        )}

        <main className="flex-1 overflow-y-auto [&>*]:animate-fade-in">
          <Outlet />
        </main>
      </div>

      <LogoutConfirmDialog
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        onConfirm={onLogout}
        title={logoutTitle}
        description={logoutDescription}
        note={logoutNote}
      />
    </div>
  )
}
