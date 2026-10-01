import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { getNotificationSettings, NOTIFICATION_SETTINGS_KEY } from '../api'

/** API-NOTI-001, shared by the settings page and the Home banner. */
export function useNotificationSettings() {
  return useCachedQuery(NOTIFICATION_SETTINGS_KEY, getNotificationSettings)
}
