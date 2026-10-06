import { useCallback, useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'

/** Keep in sync with the inline script in index.html (applies the theme before first paint). */
const STORAGE_KEY = 'evcare.theme.v2'

function readTheme(): Theme {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Storage blocked (private mode): the choice lasts for this page only.
  }
}

/** Light is the default look; the choice is remembered per browser. */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => applyTheme(theme), [theme])

  const toggleTheme = useCallback(() => setTheme(t => (t === 'dark' ? 'light' : 'dark')), [])
  return { theme, toggleTheme }
}
