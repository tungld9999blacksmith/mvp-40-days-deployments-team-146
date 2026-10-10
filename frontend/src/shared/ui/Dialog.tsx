import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { cn } from './cn'
import { FOCUSABLE, isTopOverlay, pushOverlay, trapTab } from './overlayStack'

interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  /** `alertdialog` for destructive confirmations (logout, delete). */
  role?: 'dialog' | 'alertdialog'
  /** Element focused when the dialog opens (e.g. the "Huỷ" button). */
  initialFocusRef?: RefObject<HTMLElement | null>
  /** When false, Esc and overlay click do nothing (e.g. while a request runs). */
  dismissable?: boolean
  className?: string
}


/** Centered modal on desktop, bottom sheet on mobile. Traps focus while open. */
export default function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  role = 'dialog',
  initialFocusRef,
  dismissable = true,
  className,
}: DialogProps) {
  const titleId = useId()
  const descId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const dismissableRef = useRef(dismissable)
  dismissableRef.current = dismissable

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    const target = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel
    target?.focus()

    const id = Symbol('dialog')
    const pop = pushOverlay(id)

    function onKeyDown(event: KeyboardEvent) {
      // Only the top overlay reacts: a Dialog over a Drawer closes alone.
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
  }, [open, initialFocusRef])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
        aria-hidden
        onClick={() => dismissable && onClose()}
      />
      <div
        ref={panelRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          'relative w-full sm:max-w-sm bg-surface border border-border rounded-t-3xl sm:rounded-3xl p-6 elevation-md animate-pop-in focus:outline-none',
          className,
        )}
      >
        <h2 id={titleId} className="text-lg font-semibold text-foreground">
          {title}
        </h2>
        {description && (
          <div id={descId} className="text-sm text-muted mt-2 leading-relaxed">
            {description}
          </div>
        )}
        {children && <div className="mt-4">{children}</div>}
        {footer && <div className="mt-6 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}
