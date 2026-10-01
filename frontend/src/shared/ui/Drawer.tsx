import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from './cn'

/** Side panel on desktop, bottom sheet on mobile. Esc / overlay closes it. */
export default function Drawer({
  open,
  onClose,
  title,
  side = 'right',
  children,
  className,
}: {
  open: boolean
  onClose: () => void
  title: string
  side?: 'left' | 'right'
  children: ReactNode
  className?: string
}) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-background/80" aria-hidden onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'absolute bg-surface border-border flex flex-col focus:outline-none',
          'inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl border-t',
          side === 'right'
            ? 'sm:inset-y-0 sm:right-0 sm:left-auto sm:bottom-auto sm:max-h-none sm:w-[26rem] sm:rounded-none sm:border-t-0 sm:border-l'
            : 'sm:inset-y-0 sm:left-0 sm:right-auto sm:bottom-auto sm:max-h-none sm:w-[24rem] sm:rounded-none sm:border-t-0 sm:border-r',
          className,
        )}
      >
        <div className="flex items-center justify-between gap-3 px-5 h-14 border-b border-border flex-shrink-0">
          <h2 id={titleId} className="text-sm font-semibold text-foreground">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
