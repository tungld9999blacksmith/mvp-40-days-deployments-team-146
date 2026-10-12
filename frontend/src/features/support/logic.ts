/** "Hỗ trợ" page helpers: contact links and the assistant prefill. */

export const SUPPORT_PATH = '/support'

/** `tel:` link for a workshop phone as typed by the workshop ("024 3999 8888", "+84 ..."). */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

/** Opens the assistant with the question in the composer; `/ai?q=` prefills, never sends. */
export function askAiPath(question: string): string {
  const trimmed = question.trim()
  return trimmed ? `/ai?q=${encodeURIComponent(trimmed)}` : '/ai'
}
