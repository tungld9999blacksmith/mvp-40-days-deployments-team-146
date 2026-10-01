import { NETWORK_ERROR, TIMEOUT_ERROR } from '@/shared/api/client'
import type { LoginError, SessionNotice } from './context/AuthContext'

/** Login errors rendered as the blocking panel SCR-103 / SCR-303 (US-005 FE §4.6). */
const BLOCKING: Record<string, { title: string; message: string }> = {
  ACCOUNT_SUSPENDED: {
    title: 'Tài khoản đang bị khoá',
    message: 'Tài khoản của bạn đang bị khoá. Vui lòng liên hệ bộ phận hỗ trợ.',
  },
  ACCOUNT_INACTIVE: {
    title: 'Tài khoản ngừng hoạt động',
    message: 'Tài khoản của bạn đã ngừng hoạt động. Vui lòng liên hệ bộ phận hỗ trợ.',
  },
  EMAIL_ALREADY_LINKED: {
    title: 'Không thể đăng nhập',
    message: 'Email này đã được liên kết với một tài khoản khác. Vui lòng liên hệ bộ phận hỗ trợ.',
  },
  EMAIL_NOT_VERIFIED: {
    title: 'Email chưa xác minh',
    message: 'Email Google của bạn chưa được xác minh.',
  },
  UNSUPPORTED_SIGN_IN_PROVIDER: {
    title: 'Không thể đăng nhập',
    message: 'Vui lòng đăng nhập bằng tài khoản Google.',
  },
}

export function blockingLoginContent(
  error: LoginError | null,
  overrides: Partial<Record<string, { title: string; message: string }>> = {},
) {
  if (!error) return null
  return overrides[error.code] ?? BLOCKING[error.code] ?? null
}

/** Inline message under the Google button for non-blocking errors. */
export function inlineLoginMessage(error: LoginError | null): string | null {
  if (!error) return null
  if (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR || error.code === 'auth/network-request-failed') {
    return 'Không có kết nối mạng. Vui lòng thử lại.'
  }
  if (error.code.startsWith('auth/') || error.code === 'SIGN_IN_FAILED') {
    return 'Đăng nhập Google không thành công. Vui lòng thử lại.'
  }
  return 'Đăng nhập không thành công. Vui lòng thử lại.'
}

export const SESSION_NOTICE_TEXT: Record<Exclude<SessionNotice, null>, { tone: 'warning' | 'info'; text: string }> = {
  expired: { tone: 'warning', text: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.' },
  revoked: { tone: 'warning', text: 'Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.' },
  'logged-out': { tone: 'info', text: 'Bạn đã đăng xuất.' },
  'logged-out-offline': {
    tone: 'warning',
    text:
      'Bạn đã đăng xuất trên thiết bị này. Hệ thống chưa xác nhận thu hồi phiên do mất kết nối — hãy đăng nhập và đăng xuất lại khi có mạng nếu bạn dùng thiết bị chung.',
  },
}
