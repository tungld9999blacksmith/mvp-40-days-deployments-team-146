import { useEffect, useId, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, LifeBuoy, LogOut, Menu, WifiOff, X } from 'lucide-react'
import LogoutConfirmDialog from '@/features/auth/components/LogoutConfirmDialog'
import { useOnlineStatus } from '@/shared/hooks/useOnlineStatus'
import { cn } from '@/shared/ui/cn'
import { ICON_BUTTON } from '@/shared/ui/iconButton'
import Logo from '@/shared/ui/Logo'
import SupportLink from '@/shared/ui/SupportLink'
import ThemeToggle from '@/shared/ui/ThemeToggle'
import { isTopOverlay, pushOverlay, trapTab } from '@/shared/ui/overlayStack'

const SIDEBAR_STORAGE_KEY = 'evcare.sidebar.hidden'
const MENU_BUTTON = 'shrink-0 w-10 h-10 pointer-coarse:w-11 pointer-coarse:h-11 rounded-xl flex items-center justify-center text-muted hover:text-foreground hover:bg-card-hover transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface'

function readSidebarHidden(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
  /** Not built yet: shown greyed with "Sắp có". */
  disabled?: boolean
  /** Count shown as a pill (e.g. new quote results, unread notifications); hidden when 0. */
  badge?: number
  badgeLabel?: string
}

interface AppLayoutProps {
  nav: NavItem[]
  userName: string
  roleLabel: string
  avatarUrl?: string | null
  notificationsPath: string
  /** In-app "Hỗ trợ" page; without it the sidebar falls back to `SupportLink`. */
  supportPath?: string
  brandSuffix?: string
  /** Extra topbar control before the theme toggle (owner: the vehicle switcher). */
  headerExtra?: ReactNode
  /** Strip under the topbar, next to the offline banner (owner: the demo account notice). */
  notice?: ReactNode
  onLogout: () => Promise<unknown>
  logoutTitle?: string
  logoutDescription?: string
  logoutNote?: string
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return parts.slice(-2).map(part => part[0]?.toUpperCase() ?? '').join('') || 'EV'
}

function Sidebar({ nav, supportPath, brandSuffix, onLogoutClick, onNavigate }: {
  nav: NavItem[]
  supportPath?: string
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
          <span className="shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold text-emerald bg-emerald-dim ring-1 ring-inset ring-emerald/25">
            {brandSuffix}
          </span>
        )}
      </div>

      <p className="px-6 pt-4 pb-2 text-xs font-semibold text-sidebar-muted">Menu</p>
      <nav className="flex-1 px-3 pb-4 space-y-1 overflow-y-auto" aria-label="Điều hướng chính">
        {nav.map(({ to, label, icon: Icon, end, disabled, badge, badgeLabel }) =>
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
                    ? 'bg-sidebar-active text-sidebar-foreground font-semibold ring-1 ring-inset ring-sidebar-border [&>svg]:text-sidebar-active-foreground'
                    : 'text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-hover',
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
              {badge ? (
                <span className="ml-auto min-w-5 h-5 px-1.5 rounded-full bg-brand text-on-brand text-[11px] font-bold flex items-center justify-center" aria-label={badgeLabel ?? `${badge} mới`}>
                  {badge > 99 ? '99+' : badge}
                </span>
              ) : null}
            </NavLink>
          ),
        )}
      </nav>

      <div className="mx-3 mb-4 pt-3 space-y-1 border-t border-sidebar-border">
        {supportPath ? (
          <NavLink
            to={supportPath}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium w-full transition-colors',
                isActive
                  ? 'bg-sidebar-active text-sidebar-foreground font-semibold ring-1 ring-inset ring-sidebar-border [&>svg]:text-sidebar-active-foreground'
                  : 'text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-hover',
              )
            }
          >
            <LifeBuoy className="w-4 h-4" />
            Hỗ trợ
          </NavLink>
        ) : (
          <SupportLink label="Hỗ trợ" variant="sidebar" />
        )}
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

/** App shell: collapsible sidebar (desktop), drawer (mobile), topbar, offline banner, logout confirm. */
export default function AppLayout({
  nav,
  userName,
  roleLabel,
  avatarUrl,
  notificationsPath,
  supportPath,
  brandSuffix,
  headerExtra,
  notice,
  onLogout,
  logoutTitle,
  logoutDescription,
  logoutNote,
}: AppLayoutProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const online = useOnlineStatus()
  const sidebarId = useId()
  const drawerId = useId()
  const drawerRef = useRef<HTMLDivElement>(null)
  const drawerCloseRef = useRef<HTMLButtonElement>(null)
  const [sidebarHidden, setSidebarHidden] = useState(readSidebarHidden)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)

  useEffect(() => setDrawerOpen(false), [location.pathname])

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarHidden))
    } catch {
      // If storage is blocked, keep the choice for this mounted layout.
    }
  }, [sidebarHidden])

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 64rem)')
    const closeOnDesktop = () => {
      if (desktop.matches) setDrawerOpen(false)
    }
    desktop.addEventListener('change', closeOnDesktop)
    return () => desktop.removeEventListener('change', closeOnDesktop)
  }, [])

  useEffect(() => {
    if (!drawerOpen) return
    const previous = document.activeElement as HTMLElement | null
    drawerCloseRef.current?.focus()
    const id = Symbol('sidebar-drawer')
    const pop = pushOverlay(id)
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTopOverlay(id)) return
      if (event.key === 'Escape') {
        event.preventDefault()
        setDrawerOpen(false)
        return
      }
      trapTab(event, drawerRef.current)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      pop()
      if (!window.matchMedia('(min-width: 64rem)').matches) previous?.focus()
    }
  }, [drawerOpen])

  // Longest matching entry: `/technician/board/…` is "Lịch hẹn", not the `/technician` dashboard.
  const routes: NavItem[] = supportPath ? [...nav, { to: supportPath, label: 'Hỗ trợ', icon: LifeBuoy }] : nav
  const current = routes
    .filter(item => !item.disabled && (location.pathname === item.to || (!item.end && location.pathname.startsWith(`${item.to}/`))))
    .sort((a, b) => b.to.length - a.to.length)[0]

  const openLogout = () => {
    setDrawerOpen(false)
    setLogoutOpen(true)
  }

  return (
    <div className="flex h-screen bg-background bg-app-backdrop overflow-hidden">
      <aside
        id={sidebarId}
        aria-label="Menu desktop"
        aria-hidden={sidebarHidden}
        inert={sidebarHidden}
        className={cn(
          'hidden lg:block h-full flex-shrink-0 overflow-hidden transition-[width] duration-250 ease-in-out motion-reduce:transition-none',
          sidebarHidden ? 'w-0' : 'w-60',
        )}
      >
        <div className={cn(
          'h-full w-60 border-r border-sidebar-border transition-[transform,opacity] duration-250 ease-in-out motion-reduce:transition-none',
          sidebarHidden ? '-translate-x-full opacity-0' : 'translate-x-0 opacity-100',
        )}>
          <Sidebar nav={nav} supportPath={supportPath} brandSuffix={brandSuffix} onLogoutClick={openLogout} />
        </div>
      </aside>

      <div
        aria-hidden={!drawerOpen}
        inert={!drawerOpen}
        className={cn(
          'lg:hidden fixed inset-0 z-40 transition-[visibility] duration-0 motion-reduce:delay-0',
          drawerOpen ? 'visible' : 'invisible delay-250 pointer-events-none',
        )}
      >
        <div
          className={cn('absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity duration-250 motion-reduce:transition-none', drawerOpen ? 'opacity-100' : 'opacity-0')}
          aria-hidden
          onClick={() => setDrawerOpen(false)}
        />
        <div
          id={drawerId}
          ref={drawerRef}
          role="dialog"
          aria-modal={drawerOpen ? true : undefined}
          aria-label="Menu điều hướng"
          tabIndex={-1}
          className={cn(
            'absolute inset-y-0 left-0 w-64 max-w-[calc(100%-4rem)] border-r border-sidebar-border bg-sidebar elevation-md transition-transform duration-250 ease-in-out motion-reduce:transition-none focus:outline-none',
            drawerOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <Sidebar
            nav={nav}
            supportPath={supportPath}
            brandSuffix={brandSuffix}
            onLogoutClick={openLogout}
            onNavigate={() => setDrawerOpen(false)}
          />
          <button
            ref={drawerCloseRef}
            type="button"
            onClick={() => setDrawerOpen(false)}
            aria-label="Đóng menu"
            className={cn(MENU_BUTTON, 'absolute top-3 -right-12 bg-surface border border-border elevation-sm')}
          >
            <X className="w-5 h-5" aria-hidden />
          </button>
        </div>
      </div>

      <div inert={drawerOpen} className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-16 bg-surface/80 backdrop-blur-md border-b border-border flex items-center px-4 sm:px-6 gap-3 flex-shrink-0">
          <button
            type="button"
            onClick={() => setSidebarHidden(hidden => !hidden)}
            aria-label={sidebarHidden ? 'Hiện menu' : 'Ẩn menu'}
            title={sidebarHidden ? 'Hiện menu' : 'Ẩn menu'}
            aria-expanded={!sidebarHidden}
            aria-controls={sidebarId}
            className={cn(MENU_BUTTON, 'hidden lg:flex')}
          >
            <Menu className="w-5 h-5" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Mở menu"
            title="Mở menu"
            aria-expanded={drawerOpen}
            aria-controls={drawerId}
            className={cn(MENU_BUTTON, 'lg:hidden')}
          >
            <Menu className="w-5 h-5" aria-hidden />
          </button>
          <Logo className="hidden sm:block lg:hidden h-6 text-foreground" />
          {/* Phones: up to two lines, so the vehicle chip never squeezes the page name to "Lị…". */}
          {current && (
            <p className="min-w-0 text-sm leading-tight line-clamp-2 sm:text-base sm:leading-normal sm:line-clamp-1 font-semibold text-foreground">
              {current.label}
            </p>
          )}

          <div className="flex items-center gap-2 sm:gap-3 ml-auto">
            {headerExtra}
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
        {notice}

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
