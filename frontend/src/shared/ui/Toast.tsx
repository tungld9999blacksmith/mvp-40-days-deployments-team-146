import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react'
import { cn } from './cn'

type ToastTone = 'success' | 'warning' | 'error' | 'info'

interface ToastItem {
  id: number
  tone: ToastTone
  message: string
}

interface ToastApi {
  show: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastApi>({ show: () => {} })

const icons = { success: CheckCircle2, warning: AlertTriangle, error: AlertCircle, info: Info }
const tones: Record<ToastTone, string> = {
  success: 'text-emerald',
  warning: 'text-warning',
  error: 'text-error',
  info: 'text-muted',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => setItems(list => list.filter(t => t.id !== id)), [])

  const show = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId.current++
      setItems(list => [...list.slice(-2), { id, tone, message }])
      window.setTimeout(() => dismiss(id), 4500)
    },
    [dismiss],
  )

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="fixed z-[60] bottom-4 left-4 right-4 sm:left-auto sm:right-6 sm:bottom-6 sm:w-96 flex flex-col gap-2 pointer-events-none"
      >
        {items.map(item => {
          const Icon = icons[item.tone]
          return (
            <div
              key={item.id}
              className="pointer-events-auto flex items-start gap-3 bg-surface/90 backdrop-blur-xl border border-border rounded-2xl px-4 py-3 elevation-md animate-pop-in"
            >
              <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', tones[item.tone])} aria-hidden />
              <p className="flex-1 text-sm text-foreground">{item.message}</p>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                aria-label="Đóng thông báo"
                className="text-muted hover:text-foreground transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
