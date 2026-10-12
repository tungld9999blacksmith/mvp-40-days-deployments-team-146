import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronRight, SendHorizontal } from 'lucide-react'
import { Card } from '@/shared/ui/Card'
import RobotAvatar from '@/shared/ui/RobotAvatar'
import { cn } from '@/shared/ui/cn'
import { askAiPath } from '../logic'

const SUGGESTED_QUESTIONS = [
  'Tôi muốn đổi lịch hẹn sang ngày khác',
  'Gợi ý gói bảo dưỡng tối ưu cho xe của tôi',
  'Mốc bảo dưỡng tới cần làm những gì?',
]

/** "Hỏi AI Trợ lý": a question box and suggestions that open the chat prefilled (never auto-sent). */
export default function AskAiCard({ className }: { className?: string }) {
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    navigate(askAiPath(question))
  }

  return (
    <Card className={className}>
      <div className="flex items-center gap-2.5 mb-3">
        <RobotAvatar mood="wave" size={40} />
        <div>
          <p className="text-sm font-semibold text-foreground">Hỏi AI Trợ lý</p>
          <p className="text-xs text-muted">Trả lời ngay, kèm nguồn tài liệu chính hãng</p>
        </div>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2 rounded-xl border border-border bg-background/40 pl-3.5 pr-1.5 py-1.5 focus-within:border-emerald/40 focus-within:ring-4 focus-within:ring-emerald/15 transition-colors">
        <label htmlFor="support-ask-ai" className="sr-only">
          Câu hỏi cho AI Trợ lý
        </label>
        <input
          id="support-ask-ai"
          value={question}
          onChange={event => setQuestion(event.target.value)}
          placeholder="Bạn cần hỏi gì?"
          className="flex-1 min-w-0 bg-transparent text-sm text-foreground placeholder:text-muted outline-none py-1"
        />
        <button
          type="submit"
          aria-label="Mở AI Trợ lý với câu hỏi này"
          className="w-8 h-8 shrink-0 rounded-lg bg-brand text-on-brand flex items-center justify-center hover:brightness-110 transition-all"
        >
          <SendHorizontal className="w-4 h-4" aria-hidden />
        </button>
      </form>

      <p className="text-xs text-muted mt-4 mb-2">Hoặc chọn một câu hỏi</p>
      <div className="space-y-2">
        {SUGGESTED_QUESTIONS.map(suggestion => (
          <Link
            key={suggestion}
            to={askAiPath(suggestion)}
            className={cn(
              'group flex items-center justify-between gap-3 rounded-xl border border-border bg-background/40 px-3.5 py-2.5 text-sm text-foreground',
              'hover:border-emerald/30 hover:bg-emerald/5 transition-colors',
            )}
          >
            {suggestion}
            <ChevronRight className="w-4 h-4 text-muted flex-shrink-0 transition-transform group-hover:translate-x-0.5 group-hover:text-emerald" />
          </Link>
        ))}
      </div>
    </Card>
  )
}
