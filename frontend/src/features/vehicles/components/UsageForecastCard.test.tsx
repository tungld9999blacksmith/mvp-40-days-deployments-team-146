import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { MaintenanceForecast } from '../types'
import UsageForecastCard from './UsageForecastCard'

const forecast: MaintenanceForecast = {
  status: 'AVAILABLE', quality: 'SUFFICIENT', avgKmPerDay: 200,
  observationDays: 28, sampleDays: 29, anchorRecordedAt: '2026-10-11T02:00:00Z',
  kmForecastDate: '2026-10-17', officialTimeDueDate: '2026-12-31', projectedDueDate: '2026-10-17',
  basis: 'KM_FORECAST', possiblyReached: false, reminderRecommended: true, reminderLeadDays: 7,
  algorithmVersion: 'usage-v1', calculatedAt: '2026-10-11T03:00:00Z',
}

function render(value: MaintenanceForecast | null, historical = false) {
  return renderToStaticMarkup(<MemoryRouter><UsageForecastCard forecast={value} historical={historical} /></MemoryRouter>)
}

describe('vehicle usage forecast presentation', () => {
  it('labels the estimate separately from the manufacturer deadline', () => {
    const html = render(forecast)
    expect(html).toContain('200 km/ngày')
    expect(html).toContain('nếu duy trì mức sử dụng này')
    expect(html).toContain('không thay thế hạn bảo dưỡng')
    expect(html).toContain('Nên lên kế hoạch bảo dưỡng')
  })
  it('does not invent forecast values when history is incomplete', () => {
    const html = render({ ...forecast, status: 'INSUFFICIENT_DATA', avgKmPerDay: null })
    expect(html).toContain('Chưa đủ lịch sử')
    expect(html).not.toContain('200 km/ngày')
    expect(html).toContain('vẫn được nhắc theo mốc km và thời gian')
  })
  it('treats potentially reached forecasts as unconfirmed', () => {
    const html = render({ ...forecast, possiblyReached: true })
    expect(html).toContain('có thể đã chạm mốc')
    expect(html).toContain('cần số ODO mới')
    expect(html).not.toContain('đã quá hạn')
  })
  it('handles old contracts and erased/disabled historical forecasts', () => {
    expect(render(null)).toBe('')
    expect(render({ ...forecast, status: 'DISABLED' }, true)).toBe('')
    expect(render({ ...forecast, status: 'DISABLED' })).toContain('/notifications/settings#personalization')
  })
})
