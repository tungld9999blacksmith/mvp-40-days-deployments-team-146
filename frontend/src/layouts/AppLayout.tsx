import { useEffect, useState, type ComponentType } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, LogOut, Menu, WifiOff, X, Zap } from 'lucide-react'
import LogoutConfirmDialog from '@/features/auth/components/LogoutConfirmDialog'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'
import { cn } from '@/shared/ui/cn'
import SupportLink from '@/shared/ui/SupportLink'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
  /** Not built yet: shown greyed with "Sắp có". */
  disabled?: boolean
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
    <div className="flex h-full flex-col bg-surface">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-emerald flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-background" strokeWidth={2.5} />
        </div>
        <span className="text-foreground font-bold text-lg tracking-tight">EV Care</span>
        {brandSuffix && <span className="text-xs font-semibold text-emerald">{brandSuffix}</span>}
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto" aria-label="Điều hướng chính">
        {nav.map(({ to, label, icon: Icon, end, disabled }) =>
          disabled ? (
            <span
              key={to}
              aria-disabled="true"
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-muted/50 cursor-not-allowed"
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
              <span className="ml-auto text-[10px] font-semibold uppercase tracking-wide">Sắp có</span>
            </span>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors duration-150',
                  isActive ? 'bg-emerald/10 text-emerald' : 'text-muted hover:text-foreground hover:bg-card',
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ),
        )}
      </nav>

      <div className="px-3 pb-4 pt-4 space-y-1 border-t border-border">
        <SupportLink label="Hỗ trợ" variant="ghost" />
        <button
          type="button"
          onClick={onLogoutClick}
          className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium text-muted hover:text-error hover:bg-error/10 w-full transition-colors"
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

  const openLogout = () => {
    setDrawerOpen(false)
    setLogoutOpen(true)
  }

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <aside className="hidden lg:block w-60 flex-shrink-0 border-r border-border">
        <Sidebar nav={nav} brandSuffix={brandSuffix} onLogoutClick={openLogout} />
      </aside>

      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-background/80" aria-hidden onClick={() => setDrawerOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 border-r border-border">
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
              className="absolute top-4 -right-12 w-9 h-9 rounded-xl bg-surface border border-border flex items-center justify-center text-muted"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-16 bg-surface border-b border-border flex items-center px-4 sm:px-6 gap-3 flex-shrink-0">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Mở menu"
            className="lg:hidden w-9 h-9 rounded-xl bg-card border border-border flex items-center justify-center text-muted hover:text-foreground"
          >
            <Menu className="w-4 h-4" />
          </button>

          <div className="flex items-center gap-3 ml-auto">
            <button
              type="button"
              onClick={() => navigate(notificationsPath)}
              aria-label="Thông báo"
              className="w-9 h-9 rounded-xl bg-card border border-border flex items-center justify-center text-muted hover:text-foreground transition-colors"
            >
              <Bell className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-2.5 select-none">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" referrerPolicy="no-referrer" className="w-9 h-9 rounded-xl object-cover" />
              ) : (
                <div className="w-9 h-9 rounded-xl bg-emerald/15 flex items-center justify-center flex-shrink-0">
                  <span className="text-emerald text-xs font-bold">{initialsOf(userName)}</span>
                </div>
              )}
              <div className="hidden sm:block min-w-0">
                <div className="text-sm font-semibold text-foreground leading-tight truncate max-w-[200px]">{userName}</div>
                <div className="text-xs text-muted truncate max-w-[200px]">{roleLabel}</div>
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

        <main className="flex-1 overflow-y-auto">
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
