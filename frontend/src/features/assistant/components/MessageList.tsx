import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowDown } from 'lucide-react'
import Spinner from '@/shared/ui/Spinner'
import type { ChatState } from '../state/chatReducer'
import type { CitationDto } from '../types'
import { AssistantMessage, StreamingMessage, UserMessage } from './Messages'

const NEAR_BOTTOM_PX = 120

/**
 * Chat log: older pages load when the top sentinel is reached (scroll position kept),
 * auto-scroll only when the reader is near the bottom, otherwise "↓ Tin mới" (US-025 FE §4.1).
 */
export default function MessageList({
  state,
  onLoadOlder,
  onResend,
  onAskAgain,
  onOpenCitation,
  onHighlightDone,
  lastUnanswered,
  empty,
}: {
  state: ChatState
  onLoadOlder: () => void
  onResend: (clientMessageId: string) => void
  onAskAgain: (content: string) => void
  onOpenCitation: (citation: CitationDto) => void
  onHighlightDone: () => void
  lastUnanswered: { messageId: string; clientMessageId: string | null } | null
  empty: ReactNode
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const nearBottom = useRef(true)
  const prepend = useRef<{ height: number; top: number } | null>(null)
  const [showJump, setShowJump] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  const scrollToBottom = useCallback((smooth = false) => {
    const container = containerRef.current
    if (!container) return
    container.scrollTo({ top: container.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
    setShowJump(false)
  }, [])

  // Load older messages when the top sentinel becomes visible.
  const { hasOlder, loadingOlder } = state
  useEffect(() => {
    const container = containerRef.current
    const sentinel = sentinelRef.current
    if (!container || !sentinel || !hasOlder) return
    const observer = new IntersectionObserver(
      entries => {
        if (!entries[0]?.isIntersecting || loadingOlder) return
        prepend.current = { height: container.scrollHeight, top: container.scrollTop }
        onLoadOlder()
      },
      { root: container, rootMargin: '120px 0px 0px 0px' },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasOlder, loadingOlder, onLoadOlder])

  const firstId = state.messages[0]?.id
  // Only changes at the end of the log count as new content (older pages prepend at the top).
  const lastId = state.messages[state.messages.length - 1]?.id ?? ''
  const tailKey = `${lastId}|${state.pending.length}|${state.streaming ? 1 : 0}|${state.streaming?.draft.length ?? 0}`

  // Keep the visible message in place after older messages were prepended.
  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container || !prepend.current) return
    container.scrollTop = container.scrollHeight - prepend.current.height + prepend.current.top
    prepend.current = null
  }, [firstId])

  // New content at the end: follow it only if the reader is at the bottom.
  useLayoutEffect(() => {
    if (nearBottom.current) scrollToBottom()
    else if (lastId) setShowJump(true)
  }, [tailKey, lastId, scrollToBottom])

  // First render of each conversation → bottom, unless it opened on a search result.
  const scrolledFor = useRef<string | null>(null)
  useLayoutEffect(() => {
    if (state.loading) return
    const key = state.conversationId ?? 'new'
    if (scrolledFor.current === key) return
    scrolledFor.current = key
    if (state.highlightSeq === null) {
      nearBottom.current = true
      scrollToBottom()
    }
  }, [state.loading, state.conversationId, state.highlightSeq, scrollToBottom])

  // Jump to a message from the search results, highlight for 2 s.
  useEffect(() => {
    if (state.highlightSeq === null || state.loading) return
    const element = containerRef.current?.querySelector(`[data-seq="${state.highlightSeq}"]`)
    element?.scrollIntoView({ block: 'center' })
    const timer = window.setTimeout(onHighlightDone, 2000)
    return () => window.clearTimeout(timer)
  }, [state.highlightSeq, state.loading, onHighlightDone])

  // Screen readers get the final answer, never every token.
  const lastMessage = state.messages[state.messages.length - 1]
  useEffect(() => {
    if (lastMessage?.role === 'assistant' && !state.loading) setAnnouncement(`Trợ lý: ${lastMessage.content}`)
  }, [lastMessage, state.loading])

  const onScroll = () => {
    const container = containerRef.current
    if (!container) return
    nearBottom.current = container.scrollHeight - container.scrollTop - container.clientHeight <= NEAR_BOTTOM_PX
    if (nearBottom.current) setShowJump(false)
  }

  const pendingByMessageId = new Map(state.pending.filter(p => p.messageId).map(p => [p.messageId as string, p]))
  const unsentPending = state.pending.filter(p => !p.messageId)
  const isEmpty = !state.loading && state.messages.length === 0 && state.pending.length === 0

  return (
    <div className="relative flex-1 min-h-0">
      <div ref={containerRef} onScroll={onScroll} className="h-full overflow-y-auto px-4 sm:px-6 py-6" role="log" aria-label="Cuộc trò chuyện" aria-relevant="additions">
        <div className="max-w-3xl mx-auto space-y-5">
          <div ref={sentinelRef} aria-hidden className="h-px" />
          {loadingOlder && (
            <div className="flex justify-center">
              <Spinner className="w-4 h-4 text-muted" label="Đang tải tin cũ hơn" />
            </div>
          )}

          {isEmpty && empty}

          {state.messages.map(message =>
            message.role === 'assistant' ? (
              <AssistantMessage
                key={message.id}
                message={message}
                onOpenCitation={onOpenCitation}
                highlighted={state.highlightSeq === message.seq}
              />
            ) : (
              <UserMessage
                key={message.id}
                seq={message.seq}
                content={message.content}
                createdAt={message.createdAt}
                pending={pendingByMessageId.get(message.id)}
                highlighted={state.highlightSeq === message.seq}
                unansweredHint={
                  lastUnanswered?.messageId === message.id && !pendingByMessageId.has(message.id)
                    ? lastUnanswered.clientMessageId
                      ? 'resend'
                      : 'ask-again'
                    : null
                }
                onResend={() => {
                  const pending = pendingByMessageId.get(message.id)
                  const clientId = pending?.clientMessageId ?? lastUnanswered?.clientMessageId
                  if (clientId) onResend(clientId)
                }}
                onAskAgain={() => onAskAgain(message.content)}
              />
            ),
          )}

          {unsentPending.map(pending => (
            <UserMessage
              key={pending.clientMessageId}
              content={pending.content}
              pending={pending}
              onResend={() => onResend(pending.clientMessageId)}
            />
          ))}

          {state.streaming && state.pending.some(p => p.clientMessageId === state.streaming?.clientMessageId && p.messageId) && (
            <StreamingMessage streaming={state.streaming} />
          )}
        </div>
      </div>

      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {showJump && (
        <button
          type="button"
          onClick={() => {
            nearBottom.current = true
            scrollToBottom(true)
          }}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 rounded-full bg-surface border border-border px-3.5 py-1.5 text-xs text-foreground hover:bg-card transition-colors"
        >
          <ArrowDown className="w-3.5 h-3.5" aria-hidden />
          Tin mới
        </button>
      )}
    </div>
  )
}
