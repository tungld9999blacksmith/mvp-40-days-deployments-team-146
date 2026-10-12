import { describe, expect, it } from 'vitest'
import { askAiPath, telHref } from './logic'
import { FAQ_TOPICS } from './faq'

describe('telHref', () => {
  it('keeps digits and a leading plus only', () => {
    expect(telHref('024 3999 8888')).toBe('tel:02439998888')
    expect(telHref('+84 (24) 3999-8888')).toBe('tel:+842439998888')
  })
})

describe('askAiPath', () => {
  it('prefills the trimmed question', () => {
    expect(askAiPath('  Đổi lịch hẹn thế nào? ')).toBe(`/ai?q=${encodeURIComponent('Đổi lịch hẹn thế nào?')}`)
  })

  it('opens the empty chat for a blank question', () => {
    expect(askAiPath('   ')).toBe('/ai')
  })
})

describe('FAQ_TOPICS', () => {
  it('has unique question ids, used as React keys and anchors', () => {
    const ids = FAQ_TOPICS.flatMap(topic => topic.items.map(item => item.id))
    expect(new Set(ids).size).toBe(ids.length)
  })
})
