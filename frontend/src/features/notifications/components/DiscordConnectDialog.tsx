import { useRef } from 'react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { track } from '@/shared/utils/track'

/**
 * The Discord OAuth2 + bot flow (ENT-417) has no API yet (US-021 FE §4.3, Q-FE-NOTI-02),
 * so "Kết nối Discord" explains that instead of pretending to connect.
 */
export default function DiscordConnectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Kết nối Discord"
      description="Tính năng kết nối Discord sẽ sớm có. Vui lòng quay lại sau."
      initialFocusRef={closeRef}
      footer={
        <Button ref={closeRef} variant="secondary" onClick={onClose}>
          Đóng
        </Button>
      }
    />
  )
}

export function trackDiscordConnect(source: 'settings' | 'home_banner') {
  track('discord_connect_clicked', { source })
}
