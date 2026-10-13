import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { attentionEntries, toFeedEntry, type FeedEntry } from '@/features/notifications/feed'
import type { NotificationItem } from '@/features/notifications/types'
import Notifications from '@/features/notifications/pages/Notifications'
import OwnerLayout from './OwnerLayout'

vi.mock('@/shared/hooks/useCachedQuery', () => ({ useCachedQuery: vi.fn() }))
vi.mock('@/shared/hooks/useOnlineStatus', () => ({ useOnlineStatus: () => true }))
vi.mock('@/features/auth/context/AuthContext', () => ({ useAuth: () => ({ displayName: 'An', user: null, logout: async () => {} }) }))
vi.mock('@/features/quotes/hooks', () => ({ useUnseenQuotes: () => ({ data: { items: [] } }) }))
vi.mock('@/features/booking-lines/flow', () => ({ usePricingFlow: () => 'two_tier', legacyQuotesAllowed: () => false }))
vi.mock('@/features/vehicles/currentVehicle/CurrentVehicleChip', () => ({ default: () => null }))
vi.mock('@/features/notifications/hooks/useNotificationSettings', () => ({ useNotificationSettings: () => ({ data: { remindersEnabled: true, reminderLeadDays: 7 }, error: null, isFetching: false }) }))

const base: NotificationItem = { id: 'reminder:1', kind: 'MAINTENANCE_REMINDER', occurredAt: '2026-10-12T03:00:00Z', unread: false, reminder: { userVehicleId: 'v1', level: 'URGENT', odoMilestoneKm: 20000, resolved: false }, booking: null, followUp: null }
const snapshot = (data: FeedEntry[] | null) => ({ data, error: null, isFetching: false, fetchedAt: null, refetch: async () => {}, isLoading: data === null })
const render = () => renderToStaticMarkup(
  <MemoryRouter initialEntries={['/notifications']}>
    <Routes><Route element={<OwnerLayout />}><Route path="/notifications" element={<Notifications variant="owner" />} /></Route></Routes>
  </MemoryRouter>,
)
const sidebar = (html: string) => html.match(/<nav[^>]*aria-label="Điều hướng chính"[^>]*>([\s\S]*?)<\/nav>/)![1]

describe('owner notification badge', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shares the page count, including unresolved maintenance without unread flags', () => {
    const entries = [1, 2, 3].map(id => toFeedEntry({ ...base, id: `reminder:${id}` })!)
    vi.mocked(useCachedQuery).mockReturnValue(snapshot(entries))
    const html = render()
    expect(sidebar(html)).toContain('aria-label="3 việc cần xử lý">3</span>')
    expect(html).toContain('3 việc cần bạn xem')
    expect(attentionEntries(entries)).toHaveLength(3)
    // Both the persistent sidebar and page read the same cache key and fetcher.
    expect(vi.mocked(useCachedQuery).mock.calls.map(call => call[0])).toEqual(['notifications', 'notifications'])
    expect(vi.mocked(useCachedQuery).mock.calls[0][1]).toBe(vi.mocked(useCachedQuery).mock.calls[1][1])
  })

  it('hides the badge while loading and once all pending work is resolved', () => {
    vi.mocked(useCachedQuery).mockReturnValue(snapshot(null))
    expect(sidebar(render())).not.toContain('việc cần xử lý')
    vi.mocked(useCachedQuery).mockReturnValue(snapshot([toFeedEntry(base)!]))
    expect(sidebar(render())).toContain('aria-label="1 việc cần xử lý">1</span>')
    vi.mocked(useCachedQuery).mockReturnValue(snapshot([toFeedEntry({ ...base, reminder: { ...base.reminder!, resolved: true } })!]))
    expect(sidebar(render())).not.toContain('việc cần xử lý')
  })

  it('caps the visual badge at 99+ and preserves the full accessible count', () => {
    const entries = Array.from({ length: 105 }, (_, id) => toFeedEntry({ ...base, id: `reminder:${id}` })!)
    vi.mocked(useCachedQuery).mockReturnValue(snapshot(entries))
    expect(sidebar(render())).toContain('aria-label="105 việc cần xử lý">99+</span>')
  })
})
