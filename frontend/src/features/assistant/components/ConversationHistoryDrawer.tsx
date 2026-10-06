import { useCallback, useEffect, useRef, useState } from 'react'
import { MessageSquare, Search, Trash2 } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import Drawer from '@/shared/ui/Drawer'
import { MarkedSnippet } from '@/shared/ui/SafeMarkdown'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { cn } from '@/shared/ui/cn'
import { useToast } from '@/shared/ui/Toast'
import { formatRelativeDay } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { getChatTransport } from '../transport/ChatTransport'
import type { ConversationDto, SearchResultDto } from '../types'

const PAGE_SIZE = 20

/** SCR-602 / SCR-603 — conversations of the vehicle, keyword search, delete (US-025 FE §4.6, §4.7). */
export default function ConversationHistoryDrawer({
  open,
  onClose,
  userVehicleId,
  currentConversationId,
  onOpenConversation,
  onOpenResult,
  onDeleted,
  onNewConversation,
}: {
  open: boolean
  onClose: () => void
  userVehicleId: string | null
  currentConversationId: string | null
  onOpenConversation: (conversation: ConversationDto) => void
  onOpenResult: (result: SearchResultDto) => void
  onDeleted: (conversationId: string) => void
  onNewConversation: () => void
}) {
  const transport = getChatTransport()
  const toast = useToast()
  const [items, setItems] = useState<ConversationDto[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResultDto[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [toDelete, setToDelete] = useState<ConversationDto | null>(null)
  const [deleting, setDeleting] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)

  const load = useCallback(
    async (next: string | null) => {
      if (!userVehicleId) return
      setError(null)
      if (next) setLoadingMore(true)
      try {
        const page = await transport.listConversations({ userVehicleId, limit: PAGE_SIZE, cursor: next })
        setItems(current => (next && current ? [...current, ...page.data] : page.data))
        setCursor(page.page.nextCursor)
        setHasMore(page.page.hasMore)
      } catch (loadError) {
        if (isApiError(loadError)) setError(loadError)
      } finally {
        setLoadingMore(false)
      }
    },
    [transport, userVehicleId],
  )

  useEffect(() => {
    if (open) void load(null)
  }, [open, load])

  // Debounced keyword search (400 ms, 2–100 chars).
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults(null)
      setSearchError(null)
      return
    }
    const timer = window.setTimeout(async () => {
      setSearching(true)
      setSearchError(null)
      try {
        const page = await transport.searchMessages({ q: q.slice(0, 100), userVehicleId: userVehicleId ?? undefined, limit: PAGE_SIZE })
        setResults(page.data)
        track('chat_history_searched', { resultCount: page.data.length })
      } catch {
        setSearchError('Không tìm được. Vui lòng thử lại.')
      } finally {
        setSearching(false)
      }
    }, 400)
    return () => window.clearTimeout(timer)
  }, [query, transport, userVehicleId])

  async function confirmDelete() {
    if (!toDelete) return
    setDeleting(true)
    try {
      await transport.deleteConversation(toDelete.id)
    } catch (deleteError) {
      // 404 = already gone: treat as deleted (API-CONV-005 is idempotent in effect).
      if (!isApiError(deleteError, 'CONVERSATION_NOT_FOUND')) {
        toast.show('Không xoá được cuộc trò chuyện. Vui lòng thử lại.', 'error')
        setDeleting(false)
        return
      }
    }
    setItems(current => current?.filter(item => item.id !== toDelete.id) ?? null)
    track('chat_conversation_deleted')
    onDeleted(toDelete.id)
    setDeleting(false)
    setToDelete(null)
  }

  const searchingMode = query.trim().length >= 2

  return (
    <>
      <Drawer open={open} onClose={onClose} title="Lịch sử trò chuyện" side="left">
        <div className="p-4 border-b border-border space-y-3">
          <label className="relative block">
            <span className="sr-only">Tìm trong lịch sử</span>
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" aria-hidden />
            <input
              type="search"
              value={query}
              maxLength={100}
              onChange={e => setQuery(e.target.value)}
              placeholder="Tìm trong lịch sử..."
              className="w-full bg-card border border-border rounded-xl pl-9 pr-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-emerald/40"
            />
          </label>
          {!searchingMode && (
            <Button variant="secondary" size="sm" fullWidth onClick={onNewConversation}>
              Cuộc trò chuyện mới
            </Button>
          )}
        </div>

        {searchingMode ? (
          <div className="p-2">
            {searching && results === null ? (
              <div className="space-y-2 p-2">
                <Skeleton className="h-14" />
                <Skeleton className="h-14" />
              </div>
            ) : searchError ? (
              <p className="p-4 text-sm text-error">{searchError}</p>
            ) : results && results.length === 0 ? (
              <EmptyState icon={<Search className="w-5 h-5" />} title={`Không tìm thấy tin nhắn nào chứa "${query.trim()}".`} />
            ) : (
              <ul>
                {results?.map(result => (
                  <li key={result.messageId}>
                    <button
                      type="button"
                      onClick={() => onOpenResult(result)}
                      className="w-full text-left rounded-xl px-3 py-3 hover:bg-card transition-colors"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-foreground truncate">{result.conversationTitle ?? 'Cuộc trò chuyện'}</span>
                        <span className="text-[11px] text-muted font-mono whitespace-nowrap">{formatRelativeDay(result.createdAt)}</span>
                      </div>
                      <p className="text-xs text-muted mt-1 line-clamp-2">
                        <span className="text-foreground">{result.role === 'user' ? 'Bạn' : 'Trợ lý'}: </span>
                        <MarkedSnippet html={result.snippet} />
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : error && items === null ? (
          <ErrorState compact onRetry={() => void load(null)} traceId={error.traceId} />
        ) : items === null ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<MessageSquare className="w-5 h-5" />}
            title="Bạn chưa có cuộc trò chuyện nào."
            action={<Button onClick={onNewConversation}>Bắt đầu trò chuyện</Button>}
          />
        ) : (
          <div className="p-2">
            <ul>
              {items.map(item => (
                <li key={item.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onOpenConversation(item)}
                    aria-current={item.id === currentConversationId ? 'page' : undefined}
                    className={cn(
                      'w-full text-left rounded-xl px-3 py-3 pr-11 transition-colors',
                      item.id === currentConversationId ? 'bg-emerald/10' : 'hover:bg-card',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn('text-sm font-medium truncate', item.id === currentConversationId ? 'text-emerald' : 'text-foreground')}>
                        {item.title ?? 'Cuộc trò chuyện'}
                      </span>
                      <span className="text-[11px] text-muted font-mono whitespace-nowrap">{formatRelativeDay(item.lastMessageAt)}</span>
                    </div>
                    {item.lastMessagePreview && <p className="text-xs text-muted mt-1 truncate">{item.lastMessagePreview}</p>}
                  </button>
                  <button
                    type="button"
                    onClick={() => setToDelete(item)}
                    aria-label={`Xoá cuộc trò chuyện ${item.title ?? ''}`}
                    className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:text-error hover:bg-error/10 transition-colors sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
            {hasMore && (
              <Button variant="ghost" size="sm" fullWidth className="mt-2" loading={loadingMore} onClick={() => void load(cursor)}>
                Tải thêm
              </Button>
            )}
          </div>
        )}
      </Drawer>

      <Dialog
        open={toDelete !== null}
        onClose={() => setToDelete(null)}
        role="alertdialog"
        title="Xoá cuộc trò chuyện này?"
        description="Toàn bộ tin nhắn sẽ bị xoá vĩnh viễn và không thể khôi phục. Lịch hẹn đã tạo từ cuộc trò chuyện vẫn được giữ."
        initialFocusRef={cancelRef}
        dismissable={!deleting}
        footer={
          <>
            <Button ref={cancelRef} variant="secondary" onClick={() => setToDelete(null)} disabled={deleting}>
              Huỷ
            </Button>
            <Button variant="danger" onClick={() => void confirmDelete()} loading={deleting}>
              Xoá
            </Button>
          </>
        }
      />
    </>
  )
}
