import { AlertCircle, RotateCw } from 'lucide-react'
import SafeMarkdown from '@/shared/ui/SafeMarkdown'
import Spinner from '@/shared/ui/Spinner'
import { cn } from '@/shared/ui/cn'
import { formatTime } from '@/shared/utils/format'
import type { PendingUserMessage, StreamingState } from '../state/chatReducer'
import type { CitationDto, MessageDto } from '../types'
import MessageCard from './MessageCard'
import RobotAvatar from '@/shared/ui/RobotAvatar'
import { Link } from 'react-router-dom'

const STAGE_TEXT: Record<string, string> = {
  retrieving: 'Đang tra cứu tài liệu chính hãng...',
  calling_tool: 'Đang kiểm tra thông tin xe...',
  generating: 'Đang soạn câu trả lời...',
  quick_booking: 'Đang tìm xưởng gần bạn và khung giờ trống...',
}

const ASSISTANT_BUBBLE = 'rounded-[22px] rounded-tl-md bg-card elevation-sm px-4 sm:px-5 py-3.5 sm:py-4 text-[15px] text-foreground leading-relaxed'

export function citationLabel(citation: CitationDto): string {
  return `${citation.title} · v${citation.version}${citation.pageNumber ? ` · tr.${citation.pageNumber}` : ''}`
}

/** Official-source chips under an answer (AC-601). None for refusals (AC-602). */
function Citations({ citations, onOpen }: { citations: CitationDto[]; onOpen: (citation: CitationDto) => void }) {
  if (!citations.length) return null
  return (
    <div className="mt-4 pt-3 border-t border-border flex flex-wrap items-center gap-1.5">
      <p className="text-xs text-muted mr-1">Nguồn chính hãng</p>
      {citations.map((citation, index) => (
        <button
          key={`${citation.title}-${citation.pageNumber}-${index}`}
          type="button"
          onClick={() => onOpen(citation)}
          aria-label={`Nguồn: ${citation.title}, phiên bản ${citation.version}${citation.pageNumber ? `, trang ${citation.pageNumber}` : ''}`}
          className="inline-flex items-center gap-1.5 min-h-8 rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground hover:bg-card-hover hover:border-emerald/40 transition-colors text-left"
        >
          <span className="font-mono font-semibold text-emerald">{index + 1}</span>
          <span>{citation.title}</span>
          <span className="font-mono text-muted">
            v{citation.version}
            {citation.pageNumber ? ` · tr.${citation.pageNumber}` : ''}
          </span>
        </button>
      ))}
    </div>
  )
}

export function AssistantMessage({
  message,
  onOpenCitation,
  highlighted,
}: {
  message: MessageDto
  onOpenCitation: (citation: CitationDto) => void
  highlighted?: boolean
}) {
  return (
    <div className="flex gap-2.5 sm:gap-3 justify-start" data-seq={message.seq}>
      <span className="sr-only">Trợ lý:</span>
      <RobotAvatar size={36} className="mt-0.5" />
      <div className="max-w-[88%] sm:max-w-2xl min-w-0">
        <div className={cn(ASSISTANT_BUBBLE, 'transition-shadow', highlighted && 'ring-2 ring-emerald')}>
          <SafeMarkdown text={message.content} />
          <Citations citations={message.citations} onOpen={onOpenCitation} />
          <MessageCard card={message.card} />
          {message.refs.bookingId && (
            <Link className="block mt-2 text-sm font-medium text-emerald hover:text-emerald-bright" to={`/bookings/${encodeURIComponent(message.refs.bookingId)}`}>
              Xem lịch hẹn
            </Link>
          )}
        </div>
        <p className="text-[11px] text-muted font-mono mt-1.5 ml-2">{formatTime(message.createdAt)}</p>
      </div>
    </div>
  )
}

export function StreamingMessage({ streaming }: { streaming: StreamingState }) {
  return (
    <div className="flex gap-2.5 sm:gap-3 justify-start" aria-hidden>
      <RobotAvatar size={36} mood={streaming.draft ? 'idle' : 'thinking'} className="mt-0.5" />
      <div className={cn(ASSISTANT_BUBBLE, 'max-w-[88%] sm:max-w-2xl min-w-0')}>
        {streaming.draft ? (
          <p className="whitespace-pre-wrap">
            {streaming.draft}
            <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom rounded-sm bg-emerald animate-pulse" />
          </p>
        ) : (
          <span className="flex items-center gap-2.5 text-sm text-muted">
            <Spinner className="w-4 h-4 text-emerald" />
            {(streaming.stage && STAGE_TEXT[streaming.stage]) || 'Đang suy nghĩ...'}
          </span>
        )}
      </div>
    </div>
  )
}

export function UserMessage({
  content,
  createdAt,
  pending,
  unansweredHint,
  highlighted,
  seq,
  onResend,
  onAskAgain,
}: {
  content: string
  createdAt?: string
  pending?: PendingUserMessage
  /** Last saved question without an answer (e.g. after reopening the app). */
  unansweredHint?: 'resend' | 'ask-again' | null
  highlighted?: boolean
  seq?: number
  onResend?: () => void
  onAskAgain?: () => void
}) {
  const status = pending?.status
  const failed = status === 'failed'
  const unanswered = status === 'unanswered' || Boolean(unansweredHint)
  return (
    <div className="flex justify-end" data-seq={seq}>
      <span className="sr-only">Bạn:</span>
      <div className="max-w-[85%] sm:max-w-xl flex flex-col items-end">
        <div
          className={cn(
            'rounded-[22px] rounded-br-md px-4 sm:px-[18px] py-3 text-[15px] leading-relaxed whitespace-pre-wrap break-words transition-shadow',
            failed ? 'bg-error-dim text-foreground border border-error/40' : 'bg-brand text-on-brand',
            status === 'sending' && 'opacity-70',
            highlighted && 'ring-2 ring-emerald ring-offset-2 ring-offset-background',
          )}
        >
          {content}
        </div>
        <div className="flex items-center gap-2 mt-1.5 mr-2 text-[11px]">
          {status === 'sending' ? (
            <Spinner className="w-3 h-3 text-muted" label="Đang gửi" />
          ) : failed || unanswered ? (
            <>
              <AlertCircle className={cn('w-3.5 h-3.5', failed ? 'text-error' : 'text-warning')} aria-hidden />
              <span className={failed ? 'text-error' : 'text-warning'}>
                {pending?.note ?? (failed ? 'Chưa gửi được.' : 'Trợ lý chưa trả lời.')}
              </span>
              {(pending || unansweredHint === 'resend') && onResend && (
                <button type="button" onClick={onResend} className="inline-flex items-center gap-1 text-emerald hover:text-emerald-bright">
                  <RotateCw className="w-3 h-3" aria-hidden />
                  Gửi lại
                </button>
              )}
              {!pending && unansweredHint === 'ask-again' && onAskAgain && (
                <button type="button" onClick={onAskAgain} className="text-emerald hover:text-emerald-bright">
                  Hỏi lại
                </button>
              )}
            </>
          ) : (
            createdAt && <span className="text-muted font-mono">{formatTime(createdAt)}</span>
          )}
        </div>
      </div>
    </div>
  )
}
