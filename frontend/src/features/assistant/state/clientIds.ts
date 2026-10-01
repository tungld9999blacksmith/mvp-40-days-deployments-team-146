/**
 * messageId → clientMessageId for questions not answered yet, so "Gửi lại" after a
 * reload reuses the same clientMessageId (BR-611) instead of creating a duplicate.
 * Only opaque ids are stored (never message content), in sessionStorage.
 */
const KEY = 'evcare.chat.clientIds'

function read(): Record<string, string> {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) ?? '{}') as Record<string, string>
  } catch {
    return {}
  }
}

function write(map: Record<string, string>) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(map))
  } catch {
    // Storage unavailable: "Hỏi lại" is offered instead of "Gửi lại".
  }
}

export function rememberClientId(messageId: string, clientMessageId: string) {
  const map = read()
  map[messageId] = clientMessageId
  write(map)
}

export function forgetClientId(messageId: string) {
  const map = read()
  if (!(messageId in map)) return
  delete map[messageId]
  write(map)
}

export function lookupClientId(messageId: string): string | null {
  return read()[messageId] ?? null
}

export function clearClientIds() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}
