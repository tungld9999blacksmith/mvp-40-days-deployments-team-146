import AskAiCard from '../components/AskAiCard'
import FaqSection from '../components/FaqSection'
import WorkshopContactCard from '../components/WorkshopContactCard'
import { page } from '@/shared/ui/page'

/**
 * "Hỗ trợ" (owner): gathers the channels that already exist — the booked workshop's hotline,
 * the AI assistant and the FAQ. No support tickets: dropped from scope in PRD v3.7.
 * Phones: workshop → assistant → FAQ. xl: workshop and FAQ in 2/3, assistant in the right rail.
 */
export default function Support() {
  return (
    <div className={page()}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Hỗ trợ</h1>
        <p className="text-muted mt-1">Liên hệ xưởng, hỏi AI Trợ lý hoặc xem câu hỏi thường gặp.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
        <WorkshopContactCard className="xl:col-span-2" />
        <AskAiCard className="xl:row-span-2 xl:sticky xl:top-8" />
        <FaqSection className="xl:col-span-2" />
      </div>
    </div>
  )
}
