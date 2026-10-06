import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import { onSessionEnd } from '@/shared/session/sessionCache'
import { useToast } from '@/shared/ui/Toast'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { getDeviceLocation } from '../quickBooking/location'
import { runQuickBooking } from '../quickBooking/runQuickBooking'
import { chatReducer, initialChatState } from '../state/chatReducer'
import { clearClientIds, forgetClientId, lookupClientId, rememberClientId } from '../state/clientIds'
import { getChatTransport } from '../transport/ChatTransport'

onSessionEnd(clearClientIds)

const PAGE_SIZE = 50

/**
 * Chat screen logic (US-025 FE §5–§7): load / paginate, send over SSE, map errors,
 * resend with the same clientMessageId, catch up on tab focus.
 */
export function useChatSession({
  conversationParam,
  userVehicleId,
  initialTitle,
  messageSeq,
}: {
  /** `undefined` = resolving `/ai`, `'new'` = empty new conversation, otherwise an id. */
  conversationParam: string | undefined
  userVehicleId: string | null
  initialTitle: string | null
  messageSeq: number | null
}) {
  const transport = getChatTransport()
  const navigate = useNavigate()
  const toast = useToast()
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const [retryAt, setRetryAt] = useState<number | null>(null)
  const [lockedReason, setLockedReason] = useState<string | null>(null)
  const [helper, setHelper] = useState<string | null>(null)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const stateRef = useRef(state)
  stateRef.current = state
  const skipLoadFor = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const busyRetried = useRef(new Set<string>())
  const [quickBusy, setQuickBusy] = useState(false)
  const quickBusyRef = useRef(false)

  // Load a conversation when the route changes.
  useEffect(() => {
    if (conversationParam !== undefined && skipLoadFor.current === conversationParam) {
      // Created while sending the first message: keep the live state and the running stream.
      skipLoadFor.current = null
      return
    }
    abortRef.current?.abort()
    if (conversationParam === undefined) return
    if (conversationParam === 'new') {
      dispatch({ type: 'reset', conversationId: null, title: null, loading: false })
      return
    }
    let cancelled = false
    dispatch({ type: 'reset', conversationId: conversationParam, title: initialTitle, loading: true })
    ;(async () => {
      try {
        const first = await transport.getMessages(conversationParam, {
          limit: PAGE_SIZE,
          before: messageSeq !== null ? messageSeq + 1 : undefined,
        })
        let messages = first.data
        // Jumped to a search result: also load what came after it.
        if (messageSeq !== null) {
          let after = messageSeq
          for (let page = 0; page < 3; page += 1) {
            const newer = await transport.getMessages(conversationParam, { limit: 100, after })
            messages = messages.concat(newer.data)
            if (!newer.page.hasMore || !newer.page.nextCursor) break
            after = Number(newer.page.nextCursor)
          }
        }
        if (cancelled) return
        dispatch({
          type: 'loaded',
          messages,
          olderCursor: first.page.nextCursor,
          hasOlder: first.page.hasMore,
          highlightSeq: messageSeq,
        })
      } catch (error) {
        if (cancelled || !isApiError(error)) return
        if (isApiError(error, 'CONVERSATION_NOT_FOUND')) {
          toast.show('Không tìm thấy cuộc trò chuyện.', 'error')
          navigate('/ai', { replace: true })
          return
        }
        setApiError(error)
        dispatch({ type: 'load-failed', error })
      }
    })()
    return () => {
      cancelled = true
    }
    // initialTitle is read at navigation time only; a new messageSeq (search result) reloads.
  }, [conversationParam, messageSeq, transport, navigate, toast])

  // Abort a running stream when leaving the screen (EF-601).
  useEffect(() => () => abortRef.current?.abort(), [])

  // Catch up on messages sent from another device when the tab comes back (no WebSocket).
  useEffect(() => {
    const onVisible = async () => {
      const current = stateRef.current
      if (document.visibilityState !== 'visible' || !current.conversationId || current.streaming || current.loading) return
      const lastSeq = current.messages[current.messages.length - 1]?.seq
      if (lastSeq === undefined) return
      try {
        const newer = await transport.getMessages(current.conversationId, { limit: 100, after: lastSeq })
        if (newer.data.length) dispatch({ type: 'merge', messages: newer.data })
      } catch {
        // best effort
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [transport])

  const loadOlder = useCallback(async () => {
    const current = stateRef.current
    if (!current.conversationId || !current.hasOlder || current.loadingOlder || !current.olderCursor) return
    dispatch({ type: 'older-start' })
    try {
      const page = await transport.getMessages(current.conversationId, { limit: PAGE_SIZE, before: Number(current.olderCursor) })
      dispatch({ type: 'older-loaded', messages: page.data, olderCursor: page.page.nextCursor, hasOlder: page.page.hasMore })
    } catch {
      dispatch({ type: 'older-failed' })
    }
  }, [transport])

  const refreshTitle = useCallback(
    async (conversationId: string) => {
      if (!userVehicleId) return
      try {
        const page = await transport.listConversations({ userVehicleId, limit: 1 })
        const latest = page.data[0]
        if (latest?.id === conversationId && latest.title) dispatch({ type: 'set-title', title: latest.title })
      } catch {
        // the title is cosmetic
      }
    },
    [transport, userVehicleId],
  )

  const send = useCallback(
    async (text: string, resendClientId?: string) => {
      const content = text.trim()
      if (!content || stateRef.current.streaming || !userVehicleId) return
      setHelper(null)
      let conversationId = stateRef.current.conversationId

      if (!conversationId) {
        try {
          const conversation = await transport.createConversation(userVehicleId)
          conversationId = conversation.id
          skipLoadFor.current = conversation.id
          dispatch({ type: 'conversation-created', conversationId: conversation.id, title: conversation.title })
          navigate(`/ai/${conversation.id}`, { replace: true })
        } catch (error) {
          if (!isApiError(error)) throw error
          if (isApiError(error, 'VEHICLE_NOT_ACTIVE')) {
            setLockedReason('Xe chưa được xác thực hoặc đã gỡ liên kết — bạn vẫn xem được lịch sử nhưng không gửi tin mới.')
          } else if (isApiError(error, 'ONBOARDING_REQUIRED')) {
            setApiError(error)
          } else {
            toast.show('Không tạo được cuộc trò chuyện. Vui lòng thử lại.', 'error')
          }
          return
        }
      }

      const clientMessageId = resendClientId ?? newId()
      const pendingBefore = stateRef.current.pending.find(item => item.clientMessageId === clientMessageId)
      dispatch({ type: 'send', clientMessageId, content })
      const controller = new AbortController()
      abortRef.current = controller
      const startedAt = Date.now()
      let firstToken = false
      let acceptedId: string | null = pendingBefore?.messageId ?? null
      track('chat_message_sent', { length: content.length })

      try {
        await transport.sendMessage(
          conversationId,
          { clientMessageId, content },
          {
            onAccepted: message => {
              acceptedId = message.id
              rememberClientId(message.id, clientMessageId)
              dispatch({ type: 'accepted', clientMessageId, message })
            },
            onStatus: stage => dispatch({ type: 'stage', stage }),
            onToken: delta => {
              if (!firstToken) {
                firstToken = true
                track('chat_first_token', { latencyMs: Date.now() - startedAt })
              }
              dispatch({ type: 'token', delta })
            },
            onCompleted: message => {
              if (acceptedId) forgetClientId(acceptedId)
              dispatch({ type: 'completed', clientMessageId, message })
              track('chat_answer_completed', { totalMs: Date.now() - startedAt, citationCount: message.citations.length })
              if (!stateRef.current.title) void refreshTitle(conversationId as string)
            },
            onError: error => {
              dispatch({ type: 'turn-failed', clientMessageId, status: 'unanswered', note: 'Trợ lý tạm thời không trả lời được.' })
              track('chat_answer_failed', { code: error.code })
            },
          },
          controller.signal,
        )
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        if (!isApiError(error)) throw error
        track('chat_answer_failed', { code: error.code })
        const accepted = acceptedId !== null
        switch (error.code) {
          case 'RATE_LIMITED': {
            const seconds = error.retryAfter ?? 60
            setRetryAt(Date.now() + seconds * 1000)
            track('chat_rate_limited', { retryAfterSeconds: seconds })
            dispatch({ type: 'turn-failed', clientMessageId, status: 'failed', note: 'Chưa gửi được.' })
            break
          }
          case 'CONVERSATION_BUSY': {
            dispatch({ type: 'turn-failed', clientMessageId, status: 'failed', note: 'Trợ lý đang trả lời tin trước, vui lòng đợi.' })
            setHelper('Trợ lý đang trả lời tin trước, vui lòng đợi.')
            if (!busyRetried.current.has(clientMessageId)) {
              busyRetried.current.add(clientMessageId)
              window.setTimeout(() => void send(content, clientMessageId), 3000)
            }
            break
          }
          case 'VEHICLE_NOT_ACTIVE':
            setLockedReason('Xe chưa được xác thực hoặc đã gỡ liên kết — bạn vẫn xem được lịch sử nhưng không gửi tin mới.')
            dispatch({ type: 'turn-failed', clientMessageId, status: 'failed', note: 'Chưa gửi được.' })
            break
          case 'CONVERSATION_NOT_FOUND':
            toast.show('Không tìm thấy cuộc trò chuyện.', 'error')
            navigate('/ai', { replace: true })
            break
          case 'ONBOARDING_REQUIRED':
            setApiError(error)
            break
          case 'INVALID_REQUEST':
            dispatch({ type: 'turn-failed', clientMessageId, status: 'failed', note: 'Chưa gửi được.' })
            toast.show('Yêu cầu không hợp lệ.', 'error')
            break
          default: {
            const offline = error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR
            dispatch({
              type: 'turn-failed',
              clientMessageId,
              status: accepted ? 'unanswered' : 'failed',
              note: accepted ? 'Trợ lý chưa trả lời.' : offline ? 'Không có kết nối mạng.' : 'Chưa gửi được.',
            })
          }
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
      }
    },
    [transport, userVehicleId, navigate, toast, refreshTitle],
  )

  /**
   * us-061 UC-1501 — the "Đặt lịch bảo dưỡng nhanh" chip: a proposal card from the backend.
   * Never sends the label as a chat question and never books (AC-1502).
   */
  const quickBooking = useCallback(
    async ({ province = null }: { province?: string | null } = {}) => {
      if (stateRef.current.streaming || quickBusyRef.current || !userVehicleId) return
      quickBusyRef.current = true
      setQuickBusy(true)
      setHelper(null)
      track('quick_booking_started', { province: Boolean(province) })
      try {
        const location = province ? null : await getDeviceLocation()
        const { conversationId, assistantMessage } = await runQuickBooking({
          transport,
          dispatch,
          conversationId: stateRef.current.conversationId,
          userVehicleId,
          clientMessageId: newId(),
          location,
          province,
          onConversationCreated: id => {
            skipLoadFor.current = id
            navigate(`/ai/${id}`, { replace: true })
          },
        })
        const card = assistantMessage.card
        track('quick_booking_result', {
          cardType: card?.type ?? 'NONE',
          locationBasis: typeof card?.locationBasis === 'string' ? card.locationBasis : null,
          hasDeviceLocation: Boolean(location),
        })
        if (!stateRef.current.title) void refreshTitle(conversationId)
      } catch (error) {
        if (!isApiError(error)) throw error
        track('quick_booking_failed', { code: error.code })
        switch (error.code) {
          case 'RATE_LIMITED':
            setRetryAt(Date.now() + (error.retryAfter ?? 60) * 1000)
            break
          case 'CONVERSATION_BUSY':
            toast.show('Trợ lý đang trả lời, thử lại sau giây lát.', 'warning')
            break
          case 'VEHICLE_NOT_ACTIVE':
            setLockedReason('Xe chưa được xác thực hoặc đã gỡ liên kết — bạn vẫn xem được lịch sử nhưng không gửi tin mới.')
            break
          case 'CONVERSATION_NOT_FOUND':
            toast.show('Không tìm thấy cuộc trò chuyện.', 'error')
            navigate('/ai', { replace: true })
            break
          case 'ONBOARDING_REQUIRED':
            setApiError(error)
            break
          case 'NOT_SUPPORTED_IN_MOCK':
            toast.show('Chế độ minh hoạ chưa hỗ trợ đặt lịch nhanh.', 'warning')
            break
          default:
            toast.show('Chưa tạo được đề xuất đặt lịch. Vui lòng thử lại.', 'error')
        }
      } finally {
        quickBusyRef.current = false
        setQuickBusy(false)
      }
    },
    [transport, userVehicleId, navigate, toast, refreshTitle],
  )

  const getState = useCallback(() => stateRef.current, [])

  const resend = useCallback(
    (clientMessageId: string) => {
      const pending = stateRef.current.pending.find(item => item.clientMessageId === clientMessageId)
      const saved = stateRef.current.messages.find(message => lookupClientId(message.id) === clientMessageId)
      const content = pending?.content ?? saved?.content
      if (content) void send(content, clientMessageId)
    },
    [send],
  )

  const abortStream = useCallback(() => abortRef.current?.abort(), [])

  // The last saved question with no answer and no local turn running (EF-601 after reload).
  const last = state.messages[state.messages.length - 1]
  const lastUnanswered =
    last && last.role === 'user' && !state.streaming && !state.pending.some(item => item.messageId === last.id)
      ? { messageId: last.id, clientMessageId: lookupClientId(last.id) }
      : null

  return {
    state,
    dispatch,
    getState,
    send,
    resend,
    quickBooking,
    quickBusy,
    loadOlder,
    abortStream,
    retryAt,
    setRetryAt,
    lockedReason,
    helper,
    apiError,
    lastUnanswered,
    transportKind: transport.kind,
  }
}
