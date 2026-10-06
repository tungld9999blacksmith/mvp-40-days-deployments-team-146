import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CalendarClock, Car, History, Plus, Sparkles, Trash2 } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import Drawer from '@/shared/ui/Drawer'
import Skeleton from '@/shared/ui/Skeleton'
import { ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { useOnboardingRequiredRedirect } from '@/features/auth/hooks/useOnboardingRequiredRedirect'
import VehicleGate from '@/features/vehicles/components/VehicleGate'
import type { VehicleSummary } from '@/features/vehicles/types'
import ChatComposer from '../components/ChatComposer'
import ChatContextPanel, { SUGGESTED_QUESTIONS } from '../components/ChatContextPanel'
import CitationDrawer from '../components/CitationDrawer'
import ConversationHistoryDrawer from '../components/ConversationHistoryDrawer'
import MessageList from '../components/MessageList'
import { useChatSession } from '../hooks/useChatSession'
import { QUICK_BOOKING_LABEL } from '../quickBooking/proposalView'
import { QuickBookingProvider, type QuickBookingActions } from '../quickBooking/QuickBookingContext'
import { useProposalActions } from '../quickBooking/useProposalActions'
import { getChatTransport } from '../transport/ChatTransport'
import type { CitationDto } from '../types'

function useCountdown(until: number | null, onDone: () => void): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (until === null) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [until])
  const remaining = until === null ? null : Math.max(0, Math.ceil((until - now) / 1000))
  useEffect(() => {
    if (remaining === 0) onDone()
  }, [remaining, onDone])
  return remaining
}

function ChatScreen({ vehicle }: { vehicle: VehicleSummary }) {
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const { conversationId: conversationParam } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const messageSeqParam = searchParams.get('messageSeq')
  const [text, setText] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [contextOpen, setContextOpen] = useState(false)
  const [citation, setCitation] = useState<CitationDto | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [resolveError, setResolveError] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const transport = getChatTransport()

  const chat = useChatSession({
    conversationParam,
    userVehicleId: vehicle.userVehicleId,
    initialTitle: (location.state as { title?: string } | null)?.title ?? null,
    messageSeq: messageSeqParam ? Number(messageSeqParam) : null,
  })
  const { state, dispatch } = chat
  useOnboardingRequiredRedirect(chat.apiError)

  const { setRetryAt } = chat
  const clearRetry = useCallback(() => setRetryAt(null), [setRetryAt])
  const retryIn = useCountdown(chat.retryAt, clearRetry)

  useEffect(() => {
    track('chat_opened', { hasConversation: Boolean(conversationParam && conversationParam !== 'new') })
    // once per screen
  }, [])

  // `/ai?q=…` from Home: prefill, never auto-send.
  useEffect(() => {
    const q = searchParams.get('q')
    if (!q) return
    setText(q.slice(0, 2000))
    const next = new URLSearchParams(searchParams)
    next.delete('q')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  // `/ai` → the latest conversation of the vehicle, or an empty new one.
  useEffect(() => {
    if (conversationParam !== undefined) return
    let cancelled = false
    setResolveError(false)
    transport
      .listConversations({ userVehicleId: vehicle.userVehicleId, limit: 1 })
      .then(page => {
        if (cancelled) return
        const latest = page.data[0]
        const suffix = searchParams.toString() ? `?${searchParams.toString()}` : ''
        if (latest) navigate(`/ai/${latest.id}${suffix}`, { replace: true, state: { title: latest.title } })
        else navigate(`/ai/new${suffix}`, { replace: true })
      })
      .catch(error => {
        if (!cancelled && isApiError(error)) setResolveError(true)
      })
    return () => {
      cancelled = true
    }
  }, [conversationParam, transport, vehicle.userVehicleId, navigate, searchParams])

  function sendText() {
    const value = text
    setText('')
    void chat.send(value)
  }

  function ask(question: string) {
    setContextOpen(false)
    void chat.send(question)
  }

  const { quickBooking } = chat
  const proposalActions = useProposalActions({ transport, dispatch, getState: chat.getState })
  const quickBusy = chat.quickBusy || Boolean(state.streaming)
  const quickActions = useMemo<QuickBookingActions>(
    () => ({ ...proposalActions, start: options => quickBooking(options), busy: quickBusy }),
    [proposalActions, quickBooking, quickBusy],
  )

  function startQuickBooking() {
    setContextOpen(false)
    void chat.send('Tôi muốn đặt lịch bảo dưỡng. Hãy hỏi ngày giờ và xưởng, sau đó tạo đề xuất để tôi xác nhận.')
  }
  const chipDisabled = Boolean(chat.lockedReason) || Boolean(retryIn) || quickBusy

  async function deleteCurrent() {
    if (!state.conversationId) return
    setDeleting(true)
    chat.abortStream()
    try {
      await transport.deleteConversation(state.conversationId)
    } catch (error) {
      if (!isApiError(error, 'CONVERSATION_NOT_FOUND')) {
        toast.show('Không xoá được cuộc trò chuyện. Vui lòng thử lại.', 'error')
        setDeleting(false)
        return
      }
    }
    track('chat_conversation_deleted')
    setDeleting(false)
    setConfirmDelete(false)
    navigate('/ai', { replace: true })
  }

  const openCitation = useCallback((next: CitationDto) => {
    setCitation(next)
    track('chat_citation_opened', { documentType: next.documentType })
  }, [])
  const onHighlightDone = useCallback(() => dispatch({ type: 'clear-highlight' }), [dispatch])

  const resolving = conversationParam === undefined
  const title = state.conversationId ? state.title ?? 'Cuộc trò chuyện' : 'Cuộc trò chuyện mới'

  // Same condition MessageList uses to render `emptyState`.
  const chatEmpty = !state.loading && state.messages.length === 0 && state.pending.length === 0
  const emptyState = (
    <div className="flex flex-col items-center text-center py-10">
      <div className="w-12 h-12 rounded-2xl bg-emerald/10 flex items-center justify-center mb-4">
        <Sparkles className="w-6 h-6 text-emerald" aria-hidden />
      </div>
      <p className="text-sm text-foreground max-w-md leading-relaxed">
        Xin chào! Tôi có thể giúp bạn tra cứu lịch bảo dưỡng, hạng mục, bảo hành và cách dùng xe theo tài liệu chính hãng.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-xl">
        <button
          type="button"
          onClick={startQuickBooking}
          disabled={chipDisabled}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-xs text-foreground hover:bg-card-hover transition-colors disabled:opacity-50"
        >
          <CalendarClock className="w-3.5 h-3.5 text-emerald" aria-hidden />
          {QUICK_BOOKING_LABEL}
        </button>
        {SUGGESTED_QUESTIONS.map(question => (
          <button
            key={question}
            type="button"
            onClick={() => ask(question)}
            disabled={Boolean(chat.lockedReason) || Boolean(retryIn)}
            className="rounded-full border border-border bg-card px-3.5 py-2 text-xs text-foreground hover:bg-card-hover transition-colors disabled:opacity-50"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="h-14 flex items-center gap-2 px-4 sm:px-6 border-b border-border flex-shrink-0">
          <div className="w-8 h-8 rounded-lg bg-emerald/10 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-4 h-4 text-emerald" aria-hidden />
          </div>
          <h1 className="text-sm font-semibold text-foreground truncate flex-1">{title}</h1>
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} icon={<History className="w-4 h-4" />} aria-label="Lịch sử">
            <span className="hidden sm:inline">Lịch sử</span>
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate('/ai/new')} icon={<Plus className="w-4 h-4" />} aria-label="Cuộc trò chuyện mới">
            <span className="hidden md:inline">Mới</span>
          </Button>
          <Button variant="ghost" size="sm" className="xl:hidden" onClick={() => setContextOpen(true)} icon={<Car className="w-4 h-4" />} aria-label="Xe của tôi" />
          {state.conversationId && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              icon={<Trash2 className="w-4 h-4" />}
              aria-label="Xoá cuộc trò chuyện"
            />
          )}
        </div>

        {chat.transportKind === 'mock' && (
          <div className="px-4 sm:px-6 pt-3">
            <Notice className="max-w-3xl mx-auto">
              Chế độ minh hoạ: câu trả lời là dữ liệu mẫu cho tới khi backend hỗ trợ hợp đồng chat mới.
            </Notice>
          </div>
        )}

        {resolving ? (
          resolveError ? (
            <ErrorState title="Không tải được cuộc trò chuyện." onRetry={() => navigate('/ai', { replace: true })} />
          ) : (
            <div className="flex-1 p-6 max-w-3xl w-full mx-auto space-y-4" aria-busy="true">
              <Skeleton className="h-16 w-2/3" />
              <Skeleton className="h-10 w-1/2 ml-auto" />
              <Skeleton className="h-24 w-3/4" />
            </div>
          )
        ) : state.loading ? (
          <div className="flex-1 p-6 max-w-3xl w-full mx-auto space-y-4" aria-busy="true">
            <Skeleton className="h-16 w-2/3" />
            <Skeleton className="h-10 w-1/2 ml-auto" />
            <Skeleton className="h-24 w-3/4" />
            <Skeleton className="h-10 w-1/3 ml-auto" />
          </div>
        ) : state.loadError ? (
          <ErrorState title="Không tải được cuộc trò chuyện." traceId={state.loadError.traceId} onRetry={() => navigate(0)} />
        ) : (
          <QuickBookingProvider value={quickActions}>
          <MessageList
            state={state}
            onLoadOlder={chat.loadOlder}
            onResend={chat.resend}
            onAskAgain={content => setText(content)}
            onOpenCitation={openCitation}
            onHighlightDone={onHighlightDone}
            lastUnanswered={chat.lastUnanswered}
            empty={emptyState}
          />
          </QuickBookingProvider>
        )}

        <ChatComposer
          value={text}
          onChange={setText}
          onSend={sendText}
          streaming={Boolean(state.streaming)}
          lockedReason={chat.lockedReason}
          retryInSeconds={retryIn}
          helper={chat.helper}
          autoFocus
        />
      </div>

      <aside className="hidden xl:block w-80 flex-shrink-0 border-l border-border bg-surface overflow-y-auto">
        <ChatContextPanel
          vehicle={vehicle}
          onAsk={ask}
          onQuickBooking={startQuickBooking}
          disabled={Boolean(state.streaming) || Boolean(chat.lockedReason) || chat.quickBusy}
          showSuggestions={!chatEmpty}
        />
      </aside>

      <Drawer open={contextOpen} onClose={() => setContextOpen(false)} title="Xe của tôi">
        <ChatContextPanel
          vehicle={vehicle}
          onAsk={ask}
          onQuickBooking={startQuickBooking}
          disabled={Boolean(state.streaming) || Boolean(chat.lockedReason) || chat.quickBusy}
        />
      </Drawer>

      <CitationDrawer citation={citation} onClose={() => setCitation(null)} />

      <ConversationHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        userVehicleId={vehicle.userVehicleId}
        currentConversationId={state.conversationId}
        onOpenConversation={conversation => {
          setHistoryOpen(false)
          navigate(`/ai/${conversation.id}`, { state: { title: conversation.title } })
        }}
        onOpenResult={result => {
          setHistoryOpen(false)
          navigate(`/ai/${result.conversationId}?messageSeq=${result.seq}`, { state: { title: result.conversationTitle } })
        }}
        onDeleted={conversationId => {
          if (conversationId === state.conversationId) {
            chat.abortStream()
            navigate('/ai', { replace: true })
          }
        }}
        onNewConversation={() => {
          setHistoryOpen(false)
          navigate('/ai/new')
        }}
      />

      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        role="alertdialog"
        title="Xoá cuộc trò chuyện này?"
        description="Toàn bộ tin nhắn sẽ bị xoá vĩnh viễn và không thể khôi phục. Lịch hẹn đã tạo từ cuộc trò chuyện vẫn được giữ."
        initialFocusRef={cancelRef}
        dismissable={!deleting}
        footer={
          <>
            <Button ref={cancelRef} variant="secondary" onClick={() => setConfirmDelete(false)} disabled={deleting}>
              Huỷ
            </Button>
            <Button variant="danger" onClick={() => void deleteCurrent()} loading={deleting}>
              Xoá
            </Button>
          </>
        }
      />
    </div>
  )
}

/** SCR-601 — chat with official-source citations (US-025 FE). */
export default function AIAssistant() {
  return (
    <div className="h-full">
      <VehicleGate
        loading={
          <div className="p-6 max-w-3xl mx-auto space-y-4" aria-busy="true">
            <Skeleton className="h-16 w-2/3" />
            <Skeleton className="h-10 w-1/2 ml-auto" />
          </div>
        }
      >
        {vehicle => <ChatScreen vehicle={vehicle} />}
      </VehicleGate>
    </div>
  )
}
