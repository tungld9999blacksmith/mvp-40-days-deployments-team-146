import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from './cn'
import { isTopOverlay, pushOverlay, trapTab } from './overlayStack'

/** Side panel on desktop, bottom sheet on mobile. Esc / overlay closes it; focus stays inside. */
export default function Drawer({
  open,
  onClose,
  title,
  side = 'right',
  children,
  className,
  width,
  dismissable = true,
}: {
  open: boolean
  onClose: () => void
  title: string
  side?: 'left' | 'right'
  children: ReactNode
  className?: string
  /** Desktop width class, e.g. `sm:w-[30rem]` (default 26rem right / 24rem left). */
  width?: string
  /** When false, Esc and overlay click do nothing (e.g. while a request runs). */
  dismissable?: boolean
}) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const dismissableRef = useRef(dismissable)
  dismissableRef.current = dismissable

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    panel?.focus()
    const id = Symbol('drawer')
    const pop = pushOverlay(id)
    const onKeyDown = (event: KeyboardEvent) => {
      // A Dialog or Drawer opened on top of this one handles the key alone.
      if (!isTopOverlay(id)) return
      if (event.key === 'Escape') {
        event.preventDefault()
        if (dismissableRef.current) onCloseRef.current()
        return
      }
      trapTab(event, panel)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      pop()
      previous?.focus?.()
    }
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
        aria-hidden
        onClick={() => dismissable && onClose()}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'absolute bg-surface border-border flex flex-col elevation-md focus:outline-none',
          'inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl border-t',
          side === 'right'
            ? `sm:inset-y-0 sm:right-0 sm:left-auto sm:max-h-none ${width ?? 'sm:w-[26rem]'} sm:rounded-none sm:border-t-0 sm:border-l`
            : `sm:inset-y-0 sm:left-0 sm:right-auto sm:max-h-none ${width ?? 'sm:w-[24rem]'} sm:rounded-none sm:border-t-0 sm:border-r`,
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
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
