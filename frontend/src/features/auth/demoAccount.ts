/**
 * Shared demo account behind "Dùng thử ngay" (backend modules/demo_account): one account for
 * every visitor, reset every 48 h. Pure helpers for the login button and the in-app banner.
 */

/** Inline message under the demo button for a failed `POST /auth/demo-session`. */
export function demoLoginErrorMessage(code: string): string {
  switch (code) {
    case 'DEMO_RATE_LIMITED':
      return 'Bạn đã thử quá nhiều lần. Vui lòng đợi một lát rồi thử lại.'
    case 'DEMO_ACCOUNT_UNAVAILABLE':
    case 'DEMO_LOGIN_DISABLED':
      return 'Tài khoản dùng thử tạm thời chưa sẵn sàng. Vui lòng thử lại sau.'
    default:
      return 'Không vào được tài khoản dùng thử. Vui lòng thử lại.'
  }
}

/** "1 ngày 5 giờ" / "3 giờ" / "45 phút" until the next reset; null when unknown or already due. */
export function formatDemoResetIn(resetsAt: string | null | undefined, now: Date = new Date()): string | null {
  if (!resetsAt) return null
  const ms = new Date(resetsAt).getTime() - now.getTime()
  if (Number.isNaN(ms) || ms <= 0) return null
  const minutes = Math.ceil(ms / 60_000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  if (days > 0) return hours > 0 ? `${days} ngày ${hours} giờ` : `${days} ngày`
  if (hours > 0) return `${hours} giờ`
  return `${minutes} phút`
}
