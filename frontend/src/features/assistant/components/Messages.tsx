import { AlertCircle, FileText, RotateCw, Sparkles } from 'lucide-react'
import SafeMarkdown from '@/shared/ui/SafeMarkdown'
import Spinner from '@/shared/ui/Spinner'
import { cn } from '@/shared/ui/cn'
import { formatTime } from '@/shared/utils/format'
import type { PendingUserMessage, StreamingState } from '../state/chatReducer'
import type { CitationDto, MessageDto } from '../types'

const STAGE_TEXT: Record<string, string> = {
  retrieving: 'Đang tra cứu tài liệu chính hãng...',
  calling_tool: 'Đang kiểm tra thông tin xe...',
  generating: 'Đang soạn câu trả lời...',
}

function AssistantAvatar() {
  return (
    <div className="w-8 h-8 rounded-xl bg-emerald/10 flex items-center justify-center flex-shrink-0 mt-0.5" aria-hidden>
      <Sparkles className="w-4 h-4 text-emerald" />
    </div>
  )
}

export function citationLabel(citation: CitationDto): string {
  return `${citation.title} · v${citation.version}${citation.pageNumber ? ` · tr.${citation.pageNumber}` : ''}`
}

/** Official-source chips under an answer (AC-601). None for refusals (AC-602). */
function Citations({ citations, onOpen }: { citations: CitationDto[]; onOpen: (citation: CitationDto) => void }) {
  if (!citations.length) return null
  return (
    <div className="mt-3">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-muted mb-1.5">Nguồn chính hãng</p>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((citation, index) => (
          <button
            key={`${citation.title}-${citation.pageNumber}-${index}`}
            type="button"
            onClick={() => onOpen(citation)}
            aria-label={`Nguồn: ${citation.title}, phiên bản ${citation.version}${citation.pageNumber ? `, trang ${citation.pageNumber}` : ''}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald/20 bg-emerald/10 px-2.5 py-1 text-xs font-mono text-emerald hover:bg-emerald/20 transition-colors text-left"
          >
            <FileText className="w-3.5 h-3.5 flex-shrink-0" aria-hidden />
            {citationLabel(citation)}
          </button>
        ))}
      </div>
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
    <div className="flex gap-3 justify-start" data-seq={message.seq}>
      <span className="sr-only">Trợ lý:</span>
      <AssistantAvatar />
      <div className="max-w-[85%] sm:max-w-2xl min-w-0">
        <div
          className={cn(
            'rounded-2xl rounded-tl-md bg-card border px-4 py-3 text-sm text-foreground leading-relaxed transition-colors',
            highlighted ? 'border-emerald' : 'border-border',
          )}
        >
          <SafeMarkdown text={message.content} />
          <Citations citations={message.citations} onOpen={onOpenCitation} />
          {/* F5/F6 cards (`message.card`) are rendered by those specs; unknown types render nothing. */}
        </div>
        <p className="text-[11px] text-muted font-mono mt-1 ml-1">{formatTime(message.createdAt)}</p>
      </div>
    </div>
  )
}

export function StreamingMessage({ streaming }: { streaming: StreamingState }) {
  return (
    <div className="flex gap-3 justify-start" aria-hidden>
      <AssistantAvatar />
      <div className="max-w-[85%] sm:max-w-2xl min-w-0 rounded-2xl rounded-tl-md bg-card border border-border px-4 py-3 text-sm text-foreground leading-relaxed">
        {streaming.draft ? (
          <p className="whitespace-pre-wrap">
            {streaming.draft}
            <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom bg-emerald animate-pulse" />
          </p>
        ) : (
          <span className="flex items-center gap-2 text-muted">
            <Spinner className="w-3.5 h-3.5" />
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
            'rounded-2xl rounded-tr-md px-4 py-3 text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words border transition-colors',
            failed ? 'bg-error/10 border-error/40' : 'bg-emerald/10 border-emerald/20',
            status === 'sending' && 'opacity-70',
            highlighted && 'border-emerald',
          )}
        >
          {content}
        </div>
        <div className="flex items-center gap-2 mt-1 mr-1 text-[11px]">
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
