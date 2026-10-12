import { useCallback, useSyncExternalStore } from 'react'

/** Tailwind `xl` (80rem): from here owner pages show their context rail beside the main column. */
export const XL_QUERY = '(min-width: 80rem)'

/** Live `matchMedia` result; false where the API is missing (tests, old browsers). */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = typeof window === 'undefined' ? undefined : window.matchMedia?.(query)
      list?.addEventListener('change', onChange)
      return () => list?.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(
    subscribe,
    () => (typeof window === 'undefined' ? false : (window.matchMedia?.(query).matches ?? false)),
    () => false,
  )
}
