import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/shared/hooks/useTheme'
import { ICON_BUTTON } from './iconButton'

/** Topbar button: shows the sun in dark mode (switch to light) and the moon in light mode. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const label = isDark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      className={ICON_BUTTON}
    >
      {/* key re-mounts the icon so it pops in on every switch */}
      <span key={theme} className="animate-pop-in">
        {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </span>
    </button>
  )
}
