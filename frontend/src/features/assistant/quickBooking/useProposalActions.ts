import { useCallback, useMemo, useRef } from 'react'
import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR, type ApiError } from '@/shared/api/client'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import type { ChatAction, ChatState } from '../state/chatReducer'
import type { ChatTransport } from '../transport/ChatTransport'
import type { MessageDto, ProposalStatus } from '../types'
import { createInFlightGuard } from './inFlightGuard'
import { patchProposalCard } from './proposalView'
import type { ProposalOutcome, ReviseChoice } from './QuickBookingContext'

const RETRY_IN_PROGRESS_MS = 1_500
const MAX_IN_PROGRESS_RETRIES = 3

const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

/** Card actions of us-061 (API-QB-02..04) with the error mapping of FE spec §3. */
export function useProposalActions({
  transport,
  dispatch,
  getState,
}: {
  transport: ChatTransport
  dispatch: (action: ChatAction) => void
  getState: () => ChatState
}) {
  const toast = useToast()
  const guard = useRef(createInFlightGuard()).current

  const patch = useCallback(
    (proposalId: string, status: ProposalStatus, extra: MessageDto[] = []) =>
      dispatch({ type: 'merge', messages: [...patchProposalCard(getState().messages, proposalId, { status }), ...extra] }),
    [dispatch, getState],
  )

  const reload = useCallback(async () => {
    const conversationId = getState().conversationId
    if (!conversationId) return
    try {
      const page = await transport.getMessages(conversationId, { limit: 50 })
      dispatch({ type: 'merge', messages: page.data })
    } catch {
      // best effort: the card keeps its last known state
    }
  }, [transport, dispatch, getState])

  /** Shared mapping for errors about the proposal itself. */
  const proposalError = useCallback(
    (proposalId: string, error: ApiError): ProposalOutcome => {
      switch (error.code) {
        case 'PROPOSAL_SLOT_FULL': {
          const message = (error.details?.message ?? null) as MessageDto | null
          patch(proposalId, 'SUPERSEDED', message ? [message] : [])
          toast.show('Khung giờ vừa hết chỗ, đã đề xuất phương án khác.', 'warning')
          track('quick_booking_slot_full', { hasNewProposal: Boolean(error.details?.proposalId) })
          return { ok: false, message: 'Khung giờ vừa hết chỗ.' }
        }
        case 'PROPOSAL_EXPIRED':
          patch(proposalId, 'EXPIRED')
          return { ok: false, message: 'Đề xuất đã hết hạn.' }
        case 'PROPOSAL_INACTIVE':
          patch(proposalId, ((error.details?.status as ProposalStatus | undefined) ?? 'SUPERSEDED'))
          return { ok: false, message: 'Đề xuất này không còn hiệu lực.' }
        case 'PROPOSAL_ALREADY_CONFIRMED':
        case 'PROPOSAL_NOT_FOUND':
        case 'PROPOSAL_IN_PROGRESS':
          void reload()
          return { ok: false, message: 'Đề xuất vừa thay đổi, đang tải lại.' }
        case 'OPEN_BOOKING_EXISTS':
          return {
            ok: false,
            message: 'Xe đã có lịch hẹn đang mở.',
            bookingId: (error.details?.bookingId as string | null | undefined) ?? null,
          }
        case 'VEHICLE_NOT_ACTIVE':
          return { ok: false, message: 'Xe chưa được xác thực hoặc đã gỡ liên kết.' }
        default: {
          const offline = error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR
          return {
            ok: false,
            message: offline ? 'Không có kết nối mạng.' : 'Chưa đặt được lịch. Vui lòng thử lại.',
            retryable: true,
          }
        }
      }
    },
    [patch, reload, toast],
  )

  const confirm = useCallback(
    (proposalId: string): Promise<ProposalOutcome> =>
      guard.run(proposalId, async () => {
        const conversationId = getState().conversationId
        if (!conversationId) return { ok: false, message: 'Chưa có cuộc trò chuyện.' }
        track('quick_booking_confirm_clicked')
        for (let attempt = 0; ; attempt += 1) {
          try {
            const result = await transport.confirmProposal(conversationId, proposalId)
            const { bookingId, bookingCode, status, ownerCancelableUntil } = result.booking
            dispatch({
              type: 'merge',
              messages: [
                ...patchProposalCard(getState().messages, proposalId, {
                  status: 'CONFIRMED',
                  booking: { bookingId, bookingCode, status, ownerCancelableUntil },
                }),
                ...(result.message ? [result.message] : []),
              ],
            })
            track('quick_booking_confirmed', { bookingStatus: status, replayed: result.replayed })
            return { ok: true }
          } catch (error) {
            if (!isApiError(error)) throw error
            if (error.code === 'PROPOSAL_IN_PROGRESS' && attempt < MAX_IN_PROGRESS_RETRIES) {
              await sleep(RETRY_IN_PROGRESS_MS)
              continue
            }
            return proposalError(proposalId, error)
          }
        }
      }),
    [guard, transport, dispatch, getState, proposalError],
  )

  const revise = useCallback(
    (proposalId: string, choice: ReviseChoice): Promise<ProposalOutcome> =>
      guard.run(proposalId, async () => {
        const conversationId = getState().conversationId
        if (!conversationId) return { ok: false, message: 'Chưa có cuộc trò chuyện.' }
        try {
          const result = await transport.reviseProposal(conversationId, proposalId, choice)
          patch(proposalId, 'SUPERSEDED', [result.message])
          track('quick_booking_revised')
          return { ok: true }
        } catch (error) {
          if (!isApiError(error)) throw error
          switch (error.code) {
            case 'SLOT_FULL':
              return { ok: false, message: 'Khung này vừa hết chỗ, bạn chọn khung khác nhé.' }
            case 'SLOT_TOO_SOON':
              return { ok: false, message: 'Khung giờ này quá sát, bạn chọn khung muộn hơn nhé.' }
            case 'SLOT_OUT_OF_HOURS':
              return { ok: false, message: 'Khung giờ ngoài giờ mở cửa của xưởng.' }
            case 'REVISE_WORKSHOP_NOT_OFFERED':
              return { ok: false, message: 'Chỉ đổi được sang các xưởng có trên thẻ.' }
            case 'CONVERSATION_BUSY':
              return { ok: false, message: 'Trợ lý đang trả lời, thử lại sau giây lát.', retryable: true }
            default:
              return proposalError(proposalId, error)
          }
        }
      }),
    [guard, transport, getState, patch, proposalError],
  )

  const cancel = useCallback(
    (proposalId: string): Promise<ProposalOutcome> =>
      guard.run(proposalId, async () => {
        const conversationId = getState().conversationId
        if (!conversationId) return { ok: false, message: 'Chưa có cuộc trò chuyện.' }
        try {
          await transport.cancelProposal(conversationId, proposalId)
          patch(proposalId, 'CANCELLED')
          track('quick_booking_cancelled')
          return { ok: true }
        } catch (error) {
          if (!isApiError(error)) throw error
          return proposalError(proposalId, error)
        }
      }),
    [guard, transport, getState, patch, proposalError],
  )

  return useMemo(() => ({ confirm, revise, cancel }), [confirm, revise, cancel])
}
