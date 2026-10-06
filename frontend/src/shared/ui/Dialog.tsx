import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { cn } from './cn'

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

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'

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

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    const target = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel
    target?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && dismissable) {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [open, dismissable, initialFocusRef])

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
