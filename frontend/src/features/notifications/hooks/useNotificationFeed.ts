import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { addDays, todayVn } from '@/features/bookings/utils'
import { listWorkshopQuotes } from '@/features/quotes/api'
import { getBoard } from '@/features/workshop-board/api'
import { listNotifications, NOTIFICATION_FEED_KEY } from '../api'
import { portalEntries, toFeedEntry, type FeedEntry } from '../feed'

async function fetchOwner() {
  const feed = await listNotifications()
  return feed.items.map(toFeedEntry).filter((entry): entry is FeedEntry => entry !== null)
}

async function fetchPortal() {
  const today = todayVn()
  const [board, quotes] = await Promise.all([
    getBoard({ from: today, to: addDays(today, 6), statuses: ['PENDING'], q: '' }),
    listWorkshopQuotes('PENDING_APPROVAL'),
  ])
  return portalEntries(board.items, quotes.items)
}

/** Sidebar and page share one cache entry and one in-flight request. */
export function useNotificationFeed(variant: 'owner' | 'portal' = 'owner', poll = false) {
  const { pathname } = useLocation()
  const query = useCachedQuery(
    variant === 'owner' ? NOTIFICATION_FEED_KEY : 'notifications:portal',
    variant === 'owner' ? fetchOwner : fetchPortal,
    60_000,
  )
  const { refetch } = query

  // Returning from a quote, appointment or survey must refresh the pending-work count.
  useEffect(() => {
    void refetch()
  }, [pathname, refetch])

  useEffect(() => {
    if (!poll) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refetch()
    }, 60_000)
    return () => window.clearInterval(timer)
  }, [poll, refetch])

  return query
}
