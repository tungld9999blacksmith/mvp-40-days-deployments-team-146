import { FileText } from 'lucide-react'
import Drawer from '@/shared/ui/Drawer'
import type { CitationDto } from '../types'

const DOCUMENT_TYPES: Record<string, string> = {
  owner_manual: 'Sách hướng dẫn sử dụng',
  maintenance_manual: 'Sổ tay bảo dưỡng',
  warranty_policy: 'Chính sách bảo hành',
  service_bulletin: 'Thông báo kỹ thuật',
}

/** SCR-604 — citation detail (snapshot at answer time, BR-603). */
export default function CitationDrawer({ citation, onClose }: { citation: CitationDto | null; onClose: () => void }) {
  return (
    <Drawer open={citation !== null} onClose={onClose} title="Chi tiết nguồn">
      {citation && (
        <div className="p-5 space-y-5">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald/10 flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5 text-emerald" aria-hidden />
            </div>
            <div>
              <p className="text-base font-semibold text-foreground">{citation.title}</p>
              <p className="text-xs text-muted mt-1">
                {DOCUMENT_TYPES[citation.documentType] ?? citation.documentType} ·{' '}
                <span className="font-mono">v{citation.version}</span>
                {citation.pageNumber ? (
                  <>
                    {' '}
                    · <span className="font-mono">Trang {citation.pageNumber}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <blockquote className="border-l-2 border-emerald/40 pl-4 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {citation.snippet}
          </blockquote>
          <p className="text-xs text-muted">Trích đoạn tài liệu tại thời điểm trả lời; kiểm tra phiên bản trước khi áp dụng.</p>
          {citation.sourceUrl?.startsWith('/api/v1/demo/documents/') && (
            <a href={citation.sourceUrl} target="_blank" rel="noreferrer" className="text-sm text-emerald">Mở trích đoạn và thông tin nguồn</a>
          )}
        </div>
      )}
    </Drawer>
  )
}
