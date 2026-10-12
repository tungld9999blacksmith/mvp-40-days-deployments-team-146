import { useEffect, useId, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { ArrowUp } from 'lucide-react'
import { cn } from '@/shared/ui/cn'
import Spinner from '@/shared/ui/Spinner'
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
  actions,
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
  /** Chips on the composer's bottom row (e.g. quick booking). */
  actions?: ReactNode
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
    <div className="bg-background px-3 sm:px-6 pt-2 pb-4">
      <div className="max-w-3xl mx-auto">
        {message && (
          <p
            id={helpId}
            role={rateLimited ? undefined : 'status'}
            aria-live={rateLimited ? 'off' : 'polite'}
            className={cn('text-xs mb-2 ml-2', tooLong || rateLimited || lockedReason ? 'text-warning' : 'text-muted')}
          >
            {message}
          </p>
        )}
        <div
          className={cn(
            'relative rounded-3xl bg-card border elevation-md pl-4 sm:pl-5 pr-2.5 pt-3 pb-2.5 transition-colors',
            'focus-within:border-emerald/50',
            tooLong ? 'border-warning' : 'border-border',
            lockedReason && 'opacity-60',
          )}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={e => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={Boolean(lockedReason)}
            aria-label="Nhập câu hỏi"
            aria-describedby={message ? helpId : undefined}
            placeholder="Nhắn cho trợ lý về bảo dưỡng, bảo hành…"
            className="block w-full resize-none bg-transparent pr-2 py-1 text-[15px] leading-5 text-foreground placeholder:text-muted focus:outline-none"
          />
          <div className="flex items-center gap-2 mt-2">
            <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">{actions}</div>
            {length >= COUNTER_FROM ? (
              <span className={cn('text-[11px] font-mono', tooLong ? 'text-warning' : 'text-muted')}>
                {length}/{MAX_MESSAGE_CHARS}
              </span>
            ) : (
              <span className="text-[11px] text-muted hidden md:inline">Enter để gửi · Shift + Enter để xuống dòng</span>
            )}
            <button
              type="button"
              onClick={onSend}
              disabled={!canSend}
              aria-label={streaming ? 'Đang trả lời' : 'Gửi'}
              className={cn(
                'w-11 h-11 flex-shrink-0 rounded-full flex items-center justify-center transition-colors',
                canSend ? 'bg-brand text-on-brand hover:bg-emerald-bright' : 'bg-card-hover text-muted cursor-not-allowed',
              )}
            >
              {streaming ? <Spinner className="w-4 h-4" /> : <ArrowUp className="w-5 h-5" strokeWidth={2.4} aria-hidden />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
