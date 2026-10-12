import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardHeader } from '@/shared/ui/Card'
import { FAQ_TOPICS } from '../faq'

/** "Câu hỏi thường gặp": native <details> rows grouped by topic, so it works without JS state. */
export default function FaqSection({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <CardHeader title="Câu hỏi thường gặp" />
      <div className="space-y-6">
        {FAQ_TOPICS.map(topic => (
          <section key={topic.id} aria-labelledby={`faq-${topic.id}`}>
            <h2 id={`faq-${topic.id}`} className="text-sm font-semibold text-foreground mb-1">
              {topic.title}
            </h2>
            <div className="divide-y divide-border">
              {topic.items.map(item => (
                <details key={item.id} id={item.id} className="group">
                  <summary className="flex items-center justify-between gap-3 py-3 cursor-pointer list-none text-sm text-foreground hover:text-emerald transition-colors [&::-webkit-details-marker]:hidden">
                    {item.question}
                    <ChevronDown className="w-4 h-4 text-muted shrink-0 transition-transform group-open:rotate-180" aria-hidden />
                  </summary>
                  <div className="pb-4 pr-7 text-sm text-muted leading-relaxed">
                    <p>{item.answer}</p>
                    {item.link && (
                      <Link
                        to={item.link.to}
                        className="inline-flex items-center gap-1 mt-2 text-sm font-medium text-emerald hover:text-emerald-bright"
                      >
                        {item.link.label}
                        <ChevronRight className="w-3.5 h-3.5" aria-hidden />
                      </Link>
                    )}
                  </div>
                </details>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Card>
  )
}
