import { useEffect, useState } from 'react'
import { apiGet, apiRequest } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Drawer from '@/shared/ui/Drawer'

type Memory = {
  id: string
  key: 'preferred_service_window' | 'preferred_workshop_id' | 'cost_display_preference'
  scope: 'account' | 'vehicle'
  value: Record<string, string>
  label: string | null
  version: number
  expires_at: string
}
type MemoryData = { enabled: boolean; read_enabled: boolean; write_enabled: boolean; items: Memory[] }
type Workshop = { id: string; name: string }
const days: Record<string, string> = { monday: 'Thứ Hai', tuesday: 'Thứ Ba', wednesday: 'Thứ Tư', thursday: 'Thứ Năm', friday: 'Thứ Sáu', saturday: 'Thứ Bảy', sunday: 'Chủ nhật' }
const periods: Record<string, string> = { morning: 'Buổi sáng', afternoon: 'Buổi chiều', evening: 'Buổi tối' }
const titles: Record<Memory['key'], string> = { preferred_service_window: 'Thời gian bảo dưỡng ưu tiên', preferred_workshop_id: 'Xưởng ưu tiên', cost_display_preference: 'Cách xem chi phí' }
const inputClass = 'w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-foreground'

function description(memory: Memory): string {
  if (memory.key === 'preferred_service_window') return `${days[memory.value.day] ?? memory.value.day} · ${periods[memory.value.period] ?? memory.value.period}`
  if (memory.key === 'preferred_workshop_id') return memory.label ?? 'Xưởng đã chọn'
  return memory.value.format === 'itemized' ? 'Xem từng hạng mục' : 'Xem tổng chi phí'
}

export function MemoryDrawer({ open, onClose, userVehicleId }: { open: boolean; onClose: () => void; userVehicleId: string }) {
  const [data, setData] = useState<MemoryData | null>(null)
  const [workshops, setWorkshops] = useState<Workshop[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Memory | null>(null)
  const [value, setValue] = useState<Record<string, string>>({})
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const path = `/agent-memory?vehicle_id=${encodeURIComponent(userVehicleId)}`

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setData(null)
    setError(null)
    setEditing(null)
    setConfirmDelete(null)
    void Promise.all([
      apiGet<MemoryData>(path, { signal: controller.signal }),
      apiGet<Workshop[]>('/agent-memory/workshops', { signal: controller.signal }),
    ]).then(([next, options]) => {
      if (!controller.signal.aborted) { setData(next); setWorkshops(options) }
    }).catch(() => { if (!controller.signal.aborted) setError('Chưa tải được thông tin đã ghi nhớ. Vui lòng đóng và mở lại.') })
    return () => controller.abort()
  }, [open, path])

  async function change(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setData(await apiGet<MemoryData>(path))
      setEditing(null)
      setConfirmDelete(null)
    } catch {
      setError('Chưa lưu được thay đổi. Vui lòng tải lại thông tin trước khi thử lại.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Thông tin đã ghi nhớ">
      <div className="p-4 space-y-5">
        <p className="text-sm text-muted">Trợ lý chỉ lưu sở thích khi bạn yêu cầu ghi nhớ. Ví dụ: “Hãy nhớ tôi thích đặt lịch chiều thứ Bảy”. Bạn có thể sửa hoặc xóa các mục đã lưu.</p>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {!data && !error && <p role="status" className="text-sm text-muted">Đang tải thông tin…</p>}
        {data && <>
          {!data.read_enabled && !data.write_enabled && <p className="text-sm text-muted">Tính năng ghi nhớ chưa được bật cho tài khoản này. Bạn vẫn có thể xem và xóa thông tin đã lưu.</p>}
          <label className="flex items-center gap-3 text-sm font-medium">
            <input type="checkbox" checked={data.enabled} disabled={busy || (!data.read_enabled && !data.write_enabled)}
              onChange={e => void change(() => apiRequest('/agent-memory/settings', { method: 'PATCH', body: { enabled: e.target.checked } }))} />
            Cho phép trợ lý ghi nhớ sở thích
          </label>
          <p className="text-xs text-muted">Tắt tính năng sẽ ngừng lưu và sử dụng sở thích. Những mục đã lưu vẫn còn cho đến khi bạn xóa hoặc chúng hết hạn.</p>
          {data.items.length === 0 ? <p className="text-sm text-muted">Chưa có sở thích nào được ghi nhớ.</p> : data.items.map(memory => (
            <div key={memory.id} className="rounded-xl border border-border p-3 space-y-2">
              <p className="text-sm font-semibold">{titles[memory.key]}</p>
              <p className="text-sm">{description(memory)}</p>
              <p className="text-xs text-muted">{memory.scope === 'vehicle' ? 'Áp dụng cho xe này' : 'Áp dụng cho tài khoản'} · Hết hạn {new Date(memory.expires_at).toLocaleDateString('vi-VN')}</p>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={busy || !data.enabled || !data.write_enabled} onClick={() => { setEditing(memory); setValue({ ...memory.value }); setConfirmDelete(null) }}>Sửa</Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(memory.id)}>Xóa</Button>
              </div>
              {editing?.id === memory.id && <form className="space-y-3" onSubmit={e => { e.preventDefault(); void change(() => apiRequest(`/agent-memory/${memory.id}`, { method: 'PATCH', body: { value, version: memory.version } })) }}>
                {memory.key === 'preferred_service_window' && <>
                  <label className="block text-sm">Ngày ưu tiên<select className={inputClass} value={value.day} onChange={e => setValue({ ...value, day: e.target.value })}>{Object.entries(days).map(([day, label]) => <option key={day} value={day}>{label}</option>)}</select></label>
                  <label className="block text-sm">Buổi ưu tiên<select className={inputClass} value={value.period} onChange={e => setValue({ ...value, period: e.target.value })}>{Object.entries(periods).map(([period, label]) => <option key={period} value={period}>{label}</option>)}</select></label>
                </>}
                {memory.key === 'preferred_workshop_id' && <label className="block text-sm">Xưởng ưu tiên<select className={inputClass} value={value.workshop_id} onChange={e => setValue({ workshop_id: e.target.value })}>{workshops.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}
                {memory.key === 'cost_display_preference' && <label className="block text-sm">Cách xem chi phí<select className={inputClass} value={value.format} onChange={e => setValue({ format: e.target.value })}><option value="itemized">Từng hạng mục</option><option value="total">Tổng chi phí</option></select></label>}
                <Button type="submit" size="sm" disabled={busy}>Lưu thay đổi</Button>
                <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(null)}>Hủy</Button>
              </form>}
              {confirmDelete === memory.id && <div className="space-y-2"><p className="text-sm">Xóa sở thích này khỏi thông tin đã ghi nhớ?</p><Button size="sm" disabled={busy} onClick={() => void change(() => apiRequest(`/agent-memory/${memory.id}`, { method: 'DELETE' }))}>Xác nhận xóa</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(null)}>Hủy</Button></div>}
            </div>
          ))}
          {data.items.length > 0 && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete('all')}>Xóa toàn bộ thông tin đã ghi nhớ</Button>}
          {confirmDelete === 'all' && <div className="space-y-2"><p className="text-sm">Xóa toàn bộ sở thích của tài khoản, bao gồm các xe khác?</p><Button size="sm" disabled={busy} onClick={() => void change(() => apiRequest('/agent-memory', { method: 'DELETE' }))}>Xác nhận xóa toàn bộ</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmDelete(null)}>Hủy</Button></div>}
        </>}
      </div>
    </Drawer>
  )
}
