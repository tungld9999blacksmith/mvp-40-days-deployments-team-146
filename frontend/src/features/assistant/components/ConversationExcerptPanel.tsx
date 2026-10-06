import { useState } from 'react'
import { ChevronDown, MessagesSquare } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Skeleton from '@/shared/ui/Skeleton'
import { ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { formatTimeDayMonth } from '@/shared/utils/format'
import { getChatTransport } from '../transport/ChatTransport'
import type { ConversationExcerpt } from '../types'

/**
 * SCR-605 — read-only conversation that led to a booking of the workshop
 * (US-025 FE §4.9). Collapsed by default; the API is only called when opened.
 */
export default function ConversationExcerptPanel({ source }: { source: { type: 'booking'; id: string } }) {
  const [open, setOpen] = useState(false)
  const [excerpt, setExcerpt] = useState<ConversationExcerpt | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [hidden, setHidden] = useState(false)
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setExcerpt(await getChatTransport().getConversationExcerpt(source))
    } catch (loadError) {
      if (!isApiError(loadError)) throw loadError
      if (isApiError(loadError, 'BOOKING_NOT_FOUND')) setHidden(true)
      else setError(loadError)
    } finally {
      setLoading(false)
    }
  }

  if (hidden) return null

  return (
    <section className="bg-card border border-border rounded-2xl elevation-sm">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          const next = !open
          setOpen(next)
          if (next && !excerpt && !loading) void load()
        }}
        className="w-full flex items-center gap-3 px-5 py-4 text-left"
      >
        <MessagesSquare className="w-4 h-4 text-muted" aria-hidden />
        <span className="flex-1 text-sm font-semibold text-foreground">Hội thoại dẫn tới yêu cầu</span>
        <ChevronDown className={cn('w-4 h-4 text-muted transition-transform', open && 'rotate-180')} aria-hidden />
      </button>

      {open && (
        <div className="px-5 pb-5 border-t border-border pt-4">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-3/4" />
              <Skeleton className="h-10 w-2/3 ml-auto" />
            </div>
          ) : error ? (
            isApiError(error, 'CONVERSATION_EXCERPT_NOT_AVAILABLE') ? (
              <p className="text-sm text-muted">
                Yêu cầu này không được tạo từ trò chuyện, hoặc khách đã xoá cuộc trò chuyện.
              </p>
            ) : (
              <ErrorState compact onRetry={() => void load()} traceId={error.traceId} />
            )
          ) : excerpt ? (
            <>
              <ol className="space-y-3">
                {excerpt.messages.map(message => {
                  const confirmed = message.id === excerpt.source.confirmedMessageId
                  const fromCustomer = message.role === 'user'
                  return (
                    <li key={message.id} className={cn('flex', fromCustomer ? 'justify-end' : 'justify-start')}>
                      <div className="max-w-[85%]">
                        <div
                          className={cn(
                            'rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap border',
                            fromCustomer ? 'bg-emerald/10 border-emerald/20 text-foreground' : 'bg-background border-border text-foreground',
                            confirmed && 'border-emerald',
                          )}
                        >
                          {message.content}
                        </div>
                        <p className={cn('text-[11px] text-muted mt-1 font-mono', fromCustomer && 'text-right')}>
                          {fromCustomer ? 'Khách' : 'Trợ lý'} · {formatTimeDayMonth(message.createdAt)}
                          {confirmed && <span className="ml-2 font-sans font-semibold text-emerald">Khách xác nhận</span>}
                        </p>
                      </div>
                    </li>
                  )
                })}
              </ol>
              <p className="text-xs text-muted mt-4">Chỉ hiển thị tối đa 20 tin nhắn gần nhất trước khi khách xác nhận.</p>
            </>
          ) : null}
        </div>
      )}
    </section>
  )
}
