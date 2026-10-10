import { describe, expect, it } from 'vitest'
import { isTopOverlay, overlayDepth, pushOverlay } from './overlayStack'

describe('overlayStack', () => {
  it('only the newest overlay is on top, and closing it gives the top back', () => {
    const drawer = Symbol('drawer')
    const dialog = Symbol('dialog')
    const popDrawer = pushOverlay(drawer)
    expect(isTopOverlay(drawer)).toBe(true)

    const popDialog = pushOverlay(dialog)
    expect(isTopOverlay(dialog)).toBe(true)
    expect(isTopOverlay(drawer)).toBe(false)
    expect(overlayDepth()).toBe(2)

    popDialog()
    expect(isTopOverlay(drawer)).toBe(true)
    popDrawer()
    expect(overlayDepth()).toBe(0)
    expect(isTopOverlay(drawer)).toBe(false)
  })

  it('closing a lower overlay first keeps the upper one on top', () => {
    const a = Symbol('a')
    const b = Symbol('b')
    const popA = pushOverlay(a)
    const popB = pushOverlay(b)
    popA()
    expect(isTopOverlay(b)).toBe(true)
    popB()
    popB() // idempotent
    expect(overlayDepth()).toBe(0)
  })
})
