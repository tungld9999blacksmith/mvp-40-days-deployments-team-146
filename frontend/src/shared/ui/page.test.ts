import { describe, expect, it } from 'vitest'
import { page } from './page'

describe('page', () => {
  it('pads every page the same way and picks one of three widths', () => {
    expect(page()).toBe('p-4 sm:p-6 xl:p-8')
    expect(page('reading')).toBe('p-4 sm:p-6 xl:p-8 max-w-3xl')
    expect(page('ticket')).toBe('p-4 sm:p-6 xl:p-8 max-w-xl mx-auto')
  })
})
