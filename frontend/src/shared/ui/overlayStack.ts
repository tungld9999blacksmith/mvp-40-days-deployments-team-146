/**
 * Stack of open overlays (Dialog, Drawer). Only the top one handles Esc and keeps
 * focus inside itself, so a Dialog opened from a Drawer closes alone
 * (bao-gia-hai-tang re-review OV7). Pure module state, no React.
 */

export type OverlayId = symbol

const stack: OverlayId[] = []

/** Register an overlay as the new top; returns the function that removes it. */
export function pushOverlay(id: OverlayId = Symbol('overlay')): () => void {
  stack.push(id)
  return () => {
    const index = stack.lastIndexOf(id)
    if (index !== -1) stack.splice(index, 1)
  }
}

export function isTopOverlay(id: OverlayId): boolean {
  return stack.length > 0 && stack[stack.length - 1] === id
}

export function overlayDepth(): number {
  return stack.length
}

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Keep Tab / Shift+Tab inside `panel`. Returns true when it handled the event. */
export function trapTab(event: KeyboardEvent, panel: HTMLElement | null): boolean {
  if (event.key !== 'Tab' || !panel) return false
  const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
  if (items.length === 0) {
    event.preventDefault()
    panel.focus()
    return true
  }
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement
  if (event.shiftKey && (active === first || !panel.contains(active))) {
    event.preventDefault()
    last.focus()
    return true
  }
  if (!event.shiftKey && (active === last || !panel.contains(active))) {
    event.preventDefault()
    first.focus()
    return true
  }
  return false
}

export { FOCUSABLE }
