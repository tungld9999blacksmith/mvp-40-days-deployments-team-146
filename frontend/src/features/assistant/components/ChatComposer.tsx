import { useEffect, useId, useLayoutEffect, useRef, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { cn } from '@/shared/ui/cn'
import { formatCountdown } from '@/shared/utils/format'

export const MAX_MESSAGE_CHARS = 2000
const COUNTER_FROM = 1800

/** Message input: Enter sends, Shift+Enter breaks the line, auto-grows to 6 lines (US-025 FE §4.4). */
export default function ChatComposer({
  value,
  onChange,
  onSend,
  streaming,
  lockedReason,
  retryInSeconds,
  helper,
  autoFocus,
}: {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  streaming: boolean
  /** Composer locked (vehicle not active...). */
  lockedReason?: string | null
  /** Rate limit countdown in seconds. */
  retryInSeconds?: number | null
  /** Transient helper (e.g. "Trợ lý đang trả lời tin trước..."). */
  helper?: string | null
  autoFocus?: boolean
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const helpId = useId()
  const length = value.length
  const tooLong = length > MAX_MESSAGE_CHARS
  const rateLimited = Boolean(retryInSeconds && retryInSeconds > 0)
  const locked = Boolean(lockedReason) || rateLimited
  const canSend = !streaming && !locked && !tooLong && value.trim().length > 0

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const lineHeight = 20
    textarea.style.height = `${Math.min(textarea.scrollHeight, lineHeight * 6 + 20)}px`
  }, [value])

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus()
  }, [autoFocus])

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Vietnamese IMEs compose with Enter: never send mid-composition.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (canSend) onSend()
    }
  }

  const message = lockedReason
    ? lockedReason
    : rateLimited
      ? `Bạn đã gửi quá nhiều tin. Vui lòng thử lại sau ${formatCountdown(retryInSeconds ?? 0)}.`
      : tooLong
        ? 'Tin nhắn tối đa 2.000 ký tự.'
        : helper

  return (
    <div className="border-t border-border bg-background px-4 sm:px-6 pt-3 pb-4">
      <div className="max-w-3xl mx-auto">
        {message && (
          <p
            id={helpId}
            role={rateLimited ? undefined : 'status'}
            aria-live={rateLimited ? 'off' : 'polite'}
            className={cn('text-xs mb-2', tooLong || rateLimited || lockedReason ? 'text-warning' : 'text-muted')}
          >
            {message}
          </p>
        )}
        <div className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={e => onChange(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={Boolean(lockedReason)}
              aria-label="Nhập câu hỏi"
              aria-describedby={message ? helpId : undefined}
              placeholder="Hỏi về bảo dưỡng, bảo hành, cách dùng xe..."
              className={cn(
                'w-full resize-none bg-card border rounded-xl px-4 py-3 text-sm leading-5 text-foreground placeholder:text-muted',
                'focus:outline-none focus:ring-1 focus:ring-emerald/40 disabled:opacity-60',
                tooLong ? 'border-warning' : 'border-border',
              )}
            />
            {length >= COUNTER_FROM && (
              <span className={cn('absolute right-3 bottom-2 text-[11px] font-mono', tooLong ? 'text-warning' : 'text-muted')}>
                {length}/{MAX_MESSAGE_CHARS}
              </span>
            )}
          </div>
          <Button
            onClick={onSend}
            disabled={!canSend}
            className="h-11"
            aria-label={streaming ? 'Đang trả lời' : 'Gửi'}
            icon={<Send className="w-4 h-4" />}
          >
            <span className="hidden sm:inline">{streaming ? 'Đang trả lời...' : 'Gửi'}</span>
          </Button>
        </div>
        <p className="text-[11px] text-muted mt-2 hidden sm:block">Enter để gửi · Shift + Enter để xuống dòng</p>
      </div>
    </div>
  )
}
