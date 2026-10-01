import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, X } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { track } from '@/shared/utils/track'
import { useNotificationSettings } from '../hooks/useNotificationSettings'
import { trackDiscordConnect } from './DiscordConnectDialog'

const DISMISS_KEY = 'evcare.discordBannerDismissed'

function isDismissed(): boolean {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * Home banner when reminders are on, Discord is enabled but not connected (US-021 FE §4.5).
 * TODO(spec): the FF shows it when the last reminder was `no_recipient`, but the API does
 * not expose delivery status (Q-FE-NOTI-01); this is the closest available condition.
 */
export default function DiscordConnectBanner() {
  const navigate = useNavigate()
  const settings = useNotificationSettings()
  const [dismissed, setDismissed] = useState(isDismissed)

  const discord = settings.data?.channels.find(channel => channel.channel === 'DISCORD')
  const visible =
    !dismissed && settings.data?.remindersEnabled === true && discord?.enabled === true && discord.status === 'NOT_CONNECTED'
  if (!visible) return null

  return (
    <div role="status" className="flex flex-wrap items-center gap-3 rounded-2xl border border-warning/20 bg-warning/10 px-4 py-3 mb-6">
      <Bell className="w-4 h-4 text-warning flex-shrink-0" aria-hidden />
      <p className="flex-1 min-w-[12rem] text-sm text-foreground">
        Bạn chưa kết nối Discord nên sẽ không nhận được nhắc bảo dưỡng.
      </p>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => {
          trackDiscordConnect('home_banner')
          navigate('/notifications/settings#channel-DISCORD')
        }}
      >
        Kết nối Discord
      </Button>
      <button
        type="button"
        aria-label="Đóng thông báo"
        className="text-muted hover:text-foreground transition-colors"
        onClick={() => {
          try {
            sessionStorage.setItem(DISMISS_KEY, '1')
          } catch {
            // ignore
          }
          setDismissed(true)
          track('discord_banner_dismissed')
        }}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
