/** Minimal Server-Sent Events parser for `fetch` streams (EventSource cannot POST or send auth). */

export interface SseEvent {
  event: string
  data: string
  id?: string
}

function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  let id: string | undefined
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) continue // comment / keep-alive `: ping`
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
    else if (field === 'id') id = value
  }
  if (data.length === 0) return null
  return { event, data: data.join('\n'), id }
}

/**
 * Incremental parser: feed decoded text chunks, get complete events. Handles
 * multi-line `data:`, events split across chunks, CRLF line endings (also a `\r`
 * at the end of one chunk followed by `\n` in the next) and comment lines.
 */
export class SseParser {
  private buffer = ''
  private pendingCR = false

  push(chunk: string): SseEvent[] {
    let text = chunk
    if (this.pendingCR) {
      text = '\r' + text
      this.pendingCR = false
    }
    if (text.endsWith('\r')) {
      this.pendingCR = true
      text = text.slice(0, -1)
    }
    this.buffer += text.replace(/\r\n?/g, '\n')
    const events: SseEvent[] = []
    let boundary = this.buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const block = this.buffer.slice(0, boundary)
      this.buffer = this.buffer.slice(boundary + 2)
      const event = parseBlock(block)
      if (event) events.push(event)
      boundary = this.buffer.indexOf('\n\n')
    }
    return events
  }

  /** Remaining complete-looking event when the stream ends without a trailing blank line. */
  flush(): SseEvent[] {
    if (this.pendingCR) this.pendingCR = false
    const rest = this.buffer
    this.buffer = ''
    const event = rest.trim() ? parseBlock(rest) : null
    return event ? [event] : []
  }
}

export class StreamIdleTimeoutError extends Error {
  constructor() {
    super('No data received from the stream')
    this.name = 'StreamIdleTimeoutError'
  }
}

/**
 * Reads an SSE response body. Aborts with `StreamIdleTimeoutError` when no byte
 * (keep-alive comments included) arrives for `idleTimeoutMs` (US-025 FE §7.4).
 */
export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SseEvent) => void,
  idleTimeoutMs: number,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const parser = new SseParser()
  let idleTimer: number | undefined
  let timedOut = false

  const armIdle = () => {
    window.clearTimeout(idleTimer)
    idleTimer = window.setTimeout(() => {
      timedOut = true
      void reader.cancel()
    }, idleTimeoutMs)
  }

  armIdle()
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      armIdle()
      for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event)
    }
    for (const event of parser.push(decoder.decode())) onEvent(event)
    for (const event of parser.flush()) onEvent(event)
  } finally {
    window.clearTimeout(idleTimer)
  }
  if (timedOut) throw new StreamIdleTimeoutError()
}
