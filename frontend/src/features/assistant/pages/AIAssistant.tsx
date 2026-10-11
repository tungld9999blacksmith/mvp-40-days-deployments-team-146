import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { BatteryCharging, CalendarClock, Car, CircleDot, History, Plus, ShieldCheck, Trash2, Wrench, type LucideIcon } from 'lucide-react'
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
import { vehicleDisplayName } from '@/shared/domain/labels'
import { cn } from '@/shared/ui/cn'
import ChatComposer from '../components/ChatComposer'
import ChatContextPanel, { SUGGESTED_QUESTIONS } from '../components/ChatContextPanel'
import CitationDrawer from '../components/CitationDrawer'
import ConversationHistoryDrawer from '../components/ConversationHistoryDrawer'
import MessageList from '../components/MessageList'
import RobotAvatar, { RobotMascot } from '@/shared/ui/RobotAvatar'
import { useChatSession } from '../hooks/useChatSession'
import { QUICK_BOOKING_LABEL } from '../quickBooking/proposalView'
import { consumeQuickBookingIntent } from '../quickBooking/entry'
import { QuickBookingProvider, type QuickBookingActions } from '../quickBooking/QuickBookingContext'
import { useProposalActions } from '../quickBooking/useProposalActions'
import { getChatTransport } from '../transport/ChatTransport'
import { MemoryDrawer } from '../components/MemoryDrawer'
import type { CitationDto } from '../types'

/** Icon and one-line hint per SUGGESTED_QUESTIONS entry, same order. */
const STARTER_META: { icon: LucideIcon; hint: string }[] = [
  { icon: Wrench, hint: 'Theo lịch định kỳ của hãng cho xe bạn' },
  { icon: ShieldCheck, hint: 'Những hạng mục bạn không phải trả phí' },
  { icon: BatteryCharging, hint: 'Thời hạn, điều kiện và cách yêu cầu' },
  { icon: CircleDot, hint: 'Áp suất, đảo lốp và thay lốp' },
]

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
  const vehicleQuery = `?userVehicleId=${encodeURIComponent(vehicle.userVehicleId)}`
  const [searchParams, setSearchParams] = useSearchParams()
  const messageSeqParam = searchParams.get('messageSeq')
  const [text, setText] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [contextOpen, setContextOpen] = useState(false)
  const [citation, setCitation] = useState<CitationDto | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [resolveError, setResolveError] = useState(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const autoQuickBookingStarted = useRef(false)
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
    void quickBooking()
  }

  // Home can open `/ai/new?intent=quick-booking`. Consume the intent before starting so
  // route changes and React Strict Mode cannot create duplicate proposals.
  useEffect(() => {
    const remaining = consumeQuickBookingIntent(searchParams)
    if (!remaining || conversationParam === undefined || state.loading || state.loadError || autoQuickBookingStarted.current) return
    autoQuickBookingStarted.current = true
    setSearchParams(remaining, { replace: true })
    void quickBooking()
  }, [conversationParam, state.loading, state.loadError, searchParams, setSearchParams, quickBooking])

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
    navigate(`/ai${vehicleQuery}`, { replace: true })
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
  // Sized to fit with the composer on ~700px-tall viewports; hints and the intro line drop on short screens.
  const emptyState = (
    <div className="flex flex-col items-center text-center pt-1 sm:pt-4 pb-2">
      <div className="flex items-end gap-1">
        <RobotMascot mood="wave" size={80} label="Robot trợ lý vẫy tay chào" className="w-16 h-16 sm:w-20 sm:h-20" />
        <p className="mb-11 sm:mb-14 rounded-2xl rounded-bl-md bg-card elevation-sm px-3 py-1.5 text-[13px] font-semibold text-foreground">Xin chào!</p>
      </div>
      <h2 className="mt-2 text-xl sm:text-2xl font-extrabold tracking-tight leading-tight text-foreground max-w-xl">
        Hôm nay chiếc {vehicleDisplayName(vehicle.modelName, vehicle.trim)} của bạn cần gì?
      </h2>
      <p className="mt-1.5 text-sm text-muted max-w-lg leading-relaxed [@media(max-height:760px)]:hidden">
        Hỏi về bảo dưỡng, bảo hành và cách dùng xe. Mỗi câu trả lời đều kèm nguồn tài liệu chính hãng.
      </p>
      <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 w-full max-w-2xl text-left">
        <button
          type="button"
          onClick={startQuickBooking}
          disabled={chipDisabled}
          className="sm:col-span-2 flex items-center gap-3 rounded-2xl bg-brand text-on-brand px-3.5 py-2.5 min-h-12 hover:bg-emerald-bright transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span className="w-9 h-9 rounded-xl bg-card text-emerald flex items-center justify-center flex-shrink-0">
            <CalendarClock className="w-[18px] h-[18px]" aria-hidden />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-bold">{QUICK_BOOKING_LABEL}</span>
            <span className="hidden sm:block text-xs opacity-90 [@media(max-height:760px)]:hidden">
              Trợ lý tìm xưởng và giờ trống, bạn chỉ cần xác nhận
            </span>
          </span>
        </button>
        {SUGGESTED_QUESTIONS.map((question, index) => {
          const meta = STARTER_META[index]
          const Icon = meta?.icon ?? Wrench
          return (
            <button
              key={question}
              type="button"
              onClick={() => ask(question)}
              disabled={Boolean(chat.lockedReason) || Boolean(retryIn)}
              className="flex items-center gap-3 rounded-2xl bg-card elevation-sm px-3.5 py-2.5 min-h-12 text-foreground hover:bg-card-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="w-9 h-9 rounded-xl bg-emerald-dim text-emerald flex items-center justify-center flex-shrink-0">
                <Icon className="w-[18px] h-[18px]" aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold leading-snug">{question}</span>
                {meta && <span className="hidden sm:block text-xs text-muted [@media(max-height:760px)]:hidden">{meta.hint}</span>}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="min-h-16 flex items-center gap-2 sm:gap-3 px-3 sm:px-6 py-2.5 border-b border-border bg-surface flex-shrink-0">
          <RobotAvatar size={44} mood={state.streaming ? 'thinking' : 'idle'} online />
          <div className="flex-1 min-w-0">
            <h1 className="text-[15px] sm:text-base font-extrabold tracking-tight text-foreground leading-tight">Trợ lý EV Care</h1>
            <p className="text-xs sm:text-[13px] text-muted truncate">{title}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} icon={<History className="w-4 h-4" />} aria-label="Lịch sử">
            <span className="hidden sm:inline">Lịch sử</span>
          </Button>
          {chat.transportKind === 'http' && <Button variant="ghost" size="sm" onClick={() => setMemoryOpen(true)} aria-label="Thông tin đã ghi nhớ">Ghi nhớ</Button>}
          <button
            type="button"
            onClick={() => navigate(`/ai/new${vehicleQuery}`)}
            aria-label="Cuộc trò chuyện mới"
            className="inline-flex items-center justify-center gap-2 h-10 min-w-10 px-2.5 md:px-3.5 rounded-xl bg-foreground text-background text-[13px] font-semibold hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            <Plus className="w-4 h-4" aria-hidden />
            <span className="hidden md:inline">Trò chuyện mới</span>
          </button>
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
            <ErrorState title="Không tải được cuộc trò chuyện." onRetry={() => navigate(`/ai${vehicleQuery}`, { replace: true })} />
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
          actions={
            chatEmpty ? null : (
              <button
                type="button"
                onClick={startQuickBooking}
                disabled={chipDisabled}
                className={cn(
                  'inline-flex items-center gap-1.5 h-9 rounded-full bg-emerald-dim px-3.5 text-xs font-semibold text-emerald',
                  'hover:bg-emerald/15 transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <CalendarClock className="w-3.5 h-3.5" aria-hidden />
                Đặt lịch nhanh
              </button>
            )
          }
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
      <MemoryDrawer open={memoryOpen} onClose={() => setMemoryOpen(false)} userVehicleId={vehicle.userVehicleId} />

      <ConversationHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        userVehicleId={vehicle.userVehicleId}
        currentConversationId={state.conversationId}
        onOpenConversation={conversation => {
          setHistoryOpen(false)
          navigate(`/ai/${conversation.id}${vehicleQuery}`, { state: { title: conversation.title } })
        }}
        onOpenResult={result => {
          setHistoryOpen(false)
          navigate(`/ai/${result.conversationId}${vehicleQuery}&messageSeq=${result.seq}`, { state: { title: result.conversationTitle } })
        }}
        onDeleted={conversationId => {
          if (conversationId === state.conversationId) {
            chat.abortStream()
            navigate(`/ai${vehicleQuery}`, { replace: true })
          }
        }}
        onNewConversation={() => {
          setHistoryOpen(false)
          navigate(`/ai/new${vehicleQuery}`)
        }}
      />

      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        role="alertdialog"
        title="Xoá cuộc trò chuyện này?"
        description="Toàn bộ tin nhắn sẽ bị xoá vĩnh viễn và không thể khôi phục. Lịch hẹn hoặc báo giá đã tạo từ cuộc trò chuyện vẫn được giữ."
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
