import { initialServices } from '@/mocks/quote-review'
import type { ServiceItem } from '../types'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Car, CheckCircle2, X, Plus, Trash2, AlertTriangle, Edit3 } from 'lucide-react'
import ConversationExcerptPanel from '@/features/assistant/components/ConversationExcerptPanel'

export default function QuoteReview() {
  const navigate = useNavigate()
  // The quote page is still mock data; the excerpt (US-025 SCR-605) needs a real quote id.
  const quoteId = useSearchParams()[0].get('quoteId')
  const [services, setServices] = useState<ServiceItem[]>(initialServices)
  const [techNote, setTechNote] = useState('')
  const [approved, setApproved] = useState(false)

  const total = services.filter(s => s.included).reduce((sum, s) => sum + s.price, 0)

  function toggle(id: number) {
    setServices(prev => prev.map(s => s.id === id ? { ...s, included: !s.included } : s))
  }

  function updatePrice(id: number, val: string) {
    const n = parseInt(val.replace(/\D/g, '')) || 0
    setServices(prev => prev.map(s => s.id === id ? { ...s, price: n } : s))
  }

  function removeItem(id: number) {
    setServices(prev => prev.filter(s => s.id !== id))
  }

  function addItem() {
    setServices(prev => [...prev, {
      id: Date.now(), name: 'Hạng mục mới', desc: 'Mô tả...', price: 0,
      aiSuggested: false, included: true, editing: true,
    }])
  }

  function handleApprove() {
    setApproved(true)
    setTimeout(() => navigate('/technician/quotes'), 1500)
  }

  if (approved) {
    return (
      <div className="min-h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-20 h-20 rounded-full bg-emerald/10 flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 className="w-10 h-10 text-emerald" />
          </div>
          <h2 className="text-xl font-bold text-foreground mb-2">Báo giá đã được phê duyệt</h2>
          <p className="text-muted text-sm">Khách hàng sẽ nhận thông báo ngay.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 xl:p-8 max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Review Quote</h1>
        <p className="text-muted text-sm mt-1">Xem xét và phê duyệt báo giá bảo dưỡng từ AI</p>
      </div>

      {quoteId && (
        <div className="mb-5">
          <ConversationExcerptPanel source={{ type: 'quote', id: quoteId }} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Main review */}
        <div className="lg:col-span-2 space-y-4">
          {/* Vehicle info */}
          <div className="rounded-2xl p-5 flex items-center gap-4 bg-card border border-border">
            <div className="w-12 h-12 rounded-xl bg-card flex items-center justify-center flex-shrink-0 border border-border">
              <Car className="w-6 h-6 text-muted" />
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-foreground">VinFast VF6</div>
              <div className="text-xs text-muted font-mono mt-0.5">30A-12345 • Nguyễn Văn A</div>
              <div className="text-xs text-muted mt-0.5">19,500 km</div>
            </div>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold text-warning bg-warning/10 font-mono uppercase">
              Pending
            </span>
          </div>

          {/* AI suggested services */}
          <div className="rounded-2xl overflow-hidden bg-card border border-border">
            <div className="px-5 py-4 flex items-center gap-2 border-b border-border">
              <span className="text-sm font-semibold text-foreground">AI Suggested Services</span>
              <span className="ml-auto text-xs text-muted">{services.filter(s => s.included).length} / {services.length} hạng mục</span>
            </div>

            <div className="divide-y divide-border">
              {services.map(svc => (
                <div key={svc.id} className={`px-5 py-4 flex items-start gap-3 transition-colors ${!svc.included ? 'opacity-50' : ''}`}>
                  {/* Checkbox */}
                  <button
                    onClick={() => toggle(svc.id)}
                    className={`w-5 h-5 rounded-md flex items-center justify-center mt-0.5 flex-shrink-0 transition-all ${
                      svc.included ? 'bg-emerald' : 'bg-card border border-border'
                    }`}
                  >
                    {svc.included && <CheckCircle2 className="w-3 h-3 text-background" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{svc.name}</span>
                      {svc.aiSuggested && (
                        <span className="px-1.5 py-0.5 rounded text-xs text-emerald bg-emerald/10 font-medium">AI</span>
                      )}
                    </div>
                    <div className="text-xs text-muted mt-0.5">{svc.desc}</div>
                  </div>

                  {/* Editable price */}
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <input
                      type="text"
                      value={svc.price.toLocaleString()}
                      onChange={e => updatePrice(svc.id, e.target.value)}
                      className="w-32 bg-background border border-border rounded-lg px-2.5 py-1 text-sm text-right text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-emerald/40"
                    />
                    <span className="text-xs text-muted">VND</span>
                    {!svc.aiSuggested && (
                      <button onClick={() => removeItem(svc.id)} className="text-muted hover:text-error transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Add item */}
            <div className="px-5 py-3 border-t border-border">
              <button
                onClick={addItem}
                className="flex items-center gap-2 text-xs text-muted hover:text-emerald transition-colors py-1"
              >
                <Plus className="w-3.5 h-3.5" /> Thêm hạng mục
              </button>
            </div>
          </div>

          {/* Total */}
          <div className="rounded-2xl px-5 py-4 flex items-center justify-between bg-emerald/5 border border-emerald/15">
            <span className="text-sm font-semibold text-foreground">Tổng chi phí</span>
            <span className="text-xl font-bold text-emerald font-mono">{total.toLocaleString()} VND</span>
          </div>

          {/* Tech note */}
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Ghi chú kỹ thuật viên</label>
            <textarea
              value={techNote}
              onChange={e => setTechNote(e.target.value)}
              rows={3}
              placeholder="Ghi chú thêm về tình trạng xe, lưu ý đặc biệt..."
              className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-emerald/40 transition-all"
            />
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/technician/quotes')}
              className="px-5 py-2.5 rounded-xl text-sm font-semibold text-error border border-error/20 hover:bg-error/10 transition-all"
            >
              <div className="flex items-center gap-2"><X className="w-4 h-4" /> Reject</div>
            </button>
            <button
              onClick={() => {}}
              className="px-5 py-2.5 rounded-xl text-sm font-medium text-muted hover:text-foreground bg-card border border-border transition-all"
            >
              Save Changes
            </button>
            <button
              onClick={handleApprove}
              className="flex-1 py-2.5 rounded-xl text-sm font-bold bg-emerald text-background hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" /> Approve Quote
            </button>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="rounded-2xl p-5 bg-card border border-border">
            <p className="text-xs font-semibold uppercase tracking-widest text-muted mb-4">Thông tin khách hàng</p>
            <div className="space-y-3">
              {[
                ['Khách hàng', 'Nguyễn Văn A'],
                ['Model', 'VinFast VF6'],
                ['Biển số', '30A-12345'],
                ['Mileage', '19,500 km'],
                ['Ngày yêu cầu', '17/09/2026'],
              ].map(([k, v]) => (
                <div key={k} className="flex flex-col gap-0.5">
                  <span className="text-xs text-muted">{k}</span>
                  <span className="text-sm text-foreground font-medium">{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl p-4 bg-warning/5 border border-warning/15">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-warning mt-0.5 flex-shrink-0" />
              <p className="text-xs text-muted leading-relaxed">
                Sau khi phê duyệt, khách hàng sẽ nhận thông báo và có thể đặt lịch bảo dưỡng.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
