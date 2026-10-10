import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { listMyQuotes } from './api'

/** Cache key of the Home badge "Báo giá có kết quả" (API-QT-02 `unseenResult=true`, BR-1109). */
export const UNSEEN_QUOTES_KEY = 'quotes:unseen'

const fetchUnseen = () => listMyQuotes({ unseenResult: true })

export function useUnseenQuotes() {
  return useCachedQuery(UNSEEN_QUOTES_KEY, fetchUnseen, 60_000)
}
