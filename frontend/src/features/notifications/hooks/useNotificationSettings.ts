import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { getNotificationSettings, NOTIFICATION_SETTINGS_KEY } from '../api'

/** API-NOTI-001, shared by settings and the notifications summary. */
export function useNotificationSettings() {
  return useCachedQuery(NOTIFICATION_SETTINGS_KEY, getNotificationSettings)
}
