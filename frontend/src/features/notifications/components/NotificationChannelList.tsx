import { AlertCircle, Bell, Mail, MessageCircle, Send, Smartphone } from 'lucide-react'
import Badge from '@/shared/ui/Badge'
import Checkbox from '@/shared/ui/Checkbox'
import type { ChannelSetting } from '../types'

const CHANNELS: Record<string, { label: string; Icon: typeof Bell }> = {
  ZALO: { label: 'Zalo', Icon: MessageCircle },
  TELEGRAM: { label: 'Telegram', Icon: Send },
  SMS: { label: 'Tin nhắn SMS', Icon: Smartphone },
  EMAIL: { label: 'Email', Icon: Mail },
}

/** External channel rows: only available channels can be ticked (BR-506, US-021 FE §4.3). */
export default function NotificationChannelList({
  channels,
  values,
  onChange,
  disabled,
}: {
  channels: ChannelSetting[]
  values: Record<string, boolean>
  onChange: (channel: string, enabled: boolean) => void
  disabled?: boolean
}) {
  return (
    <div>
      <ul className="divide-y divide-border">
        {channels.map(channel => {
          const meta = CHANNELS[channel.channel] ?? { label: channel.channel, Icon: Bell }
          // Unknown channel values are treated as "coming soon" (API §19).
          const comingSoon = !channel.available || channel.status === 'COMING_SOON' || !CHANNELS[channel.channel]
          const enabled = values[channel.channel] ?? channel.enabled
          const notConnected = !comingSoon && channel.status === 'NOT_CONNECTED'
          return (
            <li key={channel.channel} className="py-4 first:pt-0 last:pb-0" id={`channel-${channel.channel}`}>
              <div className="flex flex-wrap items-center gap-3">
                <meta.Icon className="w-4 h-4 text-muted flex-shrink-0" aria-hidden />
                <Checkbox
                  className="flex-1 min-w-[8rem]"
                  checked={comingSoon ? false : enabled}
                  onChange={checked => onChange(channel.channel, checked)}
                  disabled={disabled || comingSoon}
                  label={meta.label}
                  description={comingSoon ? 'Kênh này sắp được hỗ trợ.' : undefined}
                />
                {comingSoon ? (
                  <Badge tone="neutral">Sắp có</Badge>
                ) : channel.status === 'CONNECTED' ? (
                  <Badge tone="success">Đã kết nối</Badge>
                ) : (
                  <Badge tone="warning">Chưa kết nối</Badge>
                )}
              </div>
              {notConnected && enabled && (
                <p className="flex items-start gap-1.5 text-xs text-warning mt-2 ml-7">
                  <AlertCircle className="w-3.5 h-3.5 mt-px flex-shrink-0" aria-hidden />
                  Bạn sẽ không nhận được nhắc qua {meta.label} cho tới khi kết nối.
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
