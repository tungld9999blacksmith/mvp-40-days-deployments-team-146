import { useState, type ReactNode } from 'react'
import { LogOut } from 'lucide-react'
import Logo from '@/shared/ui/Logo'
import { cn } from '@/shared/ui/cn'
import LogoutConfirmDialog from './LogoutConfirmDialog'

/**
 * Top bar of the screens outside the app shell (onboarding, vehicle picker): logo, page label,
 * account email and a logout that asks first. `width` aligns the bar with the page content.
 */
export default function StandaloneHeader({
  width,
  label,
  email,
  onLogout,
  logoutDialog,
}: {
  width: string
  label: ReactNode
  email?: string | null
  onLogout: () => Promise<unknown>
  logoutDialog?: { title?: string; description?: string; note?: string }
}) {
  const [logoutOpen, setLogoutOpen] = useState(false)
  return (
    <>
      <header className="h-16 bg-surface border-b border-border">
        <div className={cn(width, 'mx-auto h-full px-4 sm:px-6 flex items-center gap-3')}>
          <Logo className="h-8 text-foreground" />
          {label}
          <span className="ml-auto hidden md:inline text-sm text-muted truncate max-w-[220px]">{email}</span>
          <button
            type="button"
            onClick={() => setLogoutOpen(true)}
            className="ml-auto md:ml-2 flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-muted hover:text-error hover:bg-error/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Đăng xuất
          </button>
        </div>
      </header>
      <LogoutConfirmDialog open={logoutOpen} onClose={() => setLogoutOpen(false)} onConfirm={onLogout} {...logoutDialog} />
    </>
  )
}
