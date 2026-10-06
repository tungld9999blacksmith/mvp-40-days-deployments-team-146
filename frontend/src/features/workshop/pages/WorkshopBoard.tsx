import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiGet, apiRequest } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card, InfoRow } from '@/shared/ui/Card'
import { Navigate } from 'react-router-dom'

export const statusLabels: Record<string, string> = {
  PENDING: 'Chờ xác nhận', CONFIRMED: 'Đã xác nhận', CHECKED_IN: 'Đã tiếp nhận',
  IN_PROGRESS: 'Đang thực hiện', COMPLETED: 'Đã hoàn tất', CANCELLED: 'Đã hủy',
}
const actionLabels: Record<string, string> = { CHECK_IN: 'Tiếp nhận xe', START: 'Bắt đầu dịch vụ', COMPLETE: 'Hoàn tất dịch vụ', CANCEL: 'Hủy lịch' }
type Item = {
  bookingId: string; bookingCode: string; status: string; bookingDate: string; timeSlot: string;
  customer: { fullName: string | null }; vehicle: { modelName: string; licensePlate: string };
  milestoneLabel: string; estimatedCost: number; actualCost: number | null; allowedActions: string[];
  note: string | null; items: { itemCode: string; itemName: string; price: number }[];
  statusHistory: { fromStatus: string | null; toStatus: string; at: string; note: string | null }[];
}
export type Board = { from: string; to: string; demoNow?: string; summary: Record<string, number>; items: Item[] }
const money = (value: number) => `${new Intl.NumberFormat('vi-VN').format(value)} đ`

function useData<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const abort = new AbortController()
    setLoading(true)
    setError('')
    apiGet<T>(path, { signal: abort.signal }).then(value => {
      if (!abort.signal.aborted) setData(value)
    }).catch((e: unknown) => {
      if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Không tải được dữ liệu.')
    }).finally(() => { if (!abort.signal.aborted) setLoading(false) })
    return () => abort.abort()
  }, [path, revision])
  return { data, error, loading, reload: () => setRevision(r => r + 1) }
}

export default function WorkshopBoard() {
  const { data, error, loading, reload } = useData<Board>('/workshop-owner/bookings')
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') reload() }
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [])
  return <Navigate to="/technician/board" replace />
}

export function WorkshopBooking() {
  const { bookingId } = useParams()
  const { data, error, loading, reload } = useData<Item>(`/workshop-owner/bookings/${encodeURIComponent(bookingId ?? '')}`)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [note, setNote] = useState('')
  const [actualCost, setActualCost] = useState('')
  async function transition(action: string) {
    if (!data) return
    setBusy(true); setActionError('')
    try {
      await apiRequest(`/workshop-owner/bookings/${data.bookingId}/transitions`, { method: 'POST', body: {
        action, expectedStatus: data.status, source: 'BOARD',
        ...(action === 'CANCEL' ? { reasonCode: 'OTHER', note: note.trim() } : {}),
        ...(action === 'COMPLETE' ? { actualCost: Number(actualCost) } : {}),
      } })
      reload()
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Không cập nhật được lịch hẹn.')
      reload()
    } finally { setBusy(false) }
  }
  return <div className="p-6 xl:p-8 max-w-3xl space-y-5">
    <Link to="/technician" className="text-emerald">← Lịch hẹn của xưởng</Link>
    <h1 className="text-2xl font-bold">Xử lý lịch hẹn</h1>
    <Button variant="secondary" onClick={reload} disabled={loading || busy}>Tải lại trạng thái</Button>
    {loading && <p role="status">Đang tải…</p>}
    {(error || actionError) && <p role="alert" className="text-error">{error || actionError}</p>}
    {data && !loading && !error && <>
      <Card>
        <InfoRow label="Mã lịch hẹn" value={data.bookingCode} />
        <InfoRow label="Trạng thái" value={statusLabels[data.status] ?? data.status} />
        <InfoRow label="Khách hàng" value={data.customer.fullName ?? 'Chủ xe'} />
        <InfoRow label="Xe" value={`${data.vehicle.modelName} · ${data.vehicle.licensePlate}`} />
        <InfoRow label="Ngày giờ" value={`${data.bookingDate} · ${data.timeSlot.slice(0, 5)}`} />
        <InfoRow label="Chi phí ước tính" value={money(data.estimatedCost)} />
        {data.actualCost !== null && <InfoRow label="Chi phí thực tế đã ghi nhận" value={money(data.actualCost)} />}
        {data.note && <InfoRow label="Ghi chú" value={data.note} />}
      </Card>
      <Card><h2 className="font-semibold mb-3">Hạng mục dịch vụ</h2>{(data.items ?? []).map(item => <InfoRow key={item.itemCode} label={item.itemName} value={money(item.price)} />)}</Card>
      {data.status === 'CONFIRMED' && !data.allowedActions.includes('CHECK_IN') && <p>Tiếp nhận xe được mở vào đúng ngày hẹn.</p>}
      {data.allowedActions.includes('CANCEL') && <label className="block">Lý do hủy
        <input className="block border border-border rounded-lg p-2 bg-surface mt-1 w-full" maxLength={255} value={note} onChange={e => setNote(e.target.value)} />
      </label>}
      {data.allowedActions.includes('COMPLETE') && <label className="block">Chi phí thực tế (đ)
        <input className="block border border-border rounded-lg p-2 bg-surface mt-1" type="number" min="0" max="999999999.99" step="0.01" value={actualCost} onChange={e => setActualCost(e.target.value)} />
      </label>}
      <div className="flex flex-wrap gap-3">{data.allowedActions.map(action => <Button key={action} variant={action === 'CANCEL' ? 'danger' : 'primary'} disabled={busy || (action === 'CANCEL' && !note.trim()) || (action === 'COMPLETE' && (!actualCost || Number(actualCost) < 0 || !Number.isFinite(Number(actualCost))))} onClick={() => void transition(action)}>{actionLabels[action]}</Button>)}</div>
      <Card><h2 className="font-semibold mb-3">Lịch sử trạng thái</h2>{data.statusHistory.map((event, i) => <p key={i} className="mb-2">{new Date(event.at).toLocaleString('vi-VN')} · {statusLabels[event.toStatus] ?? event.toStatus}{event.note ? ` · ${event.note}` : ''}</p>)}</Card>
      <p className="text-sm text-muted">MVP ghi nhận trạng thái và chi phí trong bộ nhớ demo. Dữ liệu được xóa khi khởi động lại backend.</p>
    </>}
  </div>
}

export function WorkshopDemoScope() {
  return <div className="p-6 space-y-4"><h1 className="text-2xl font-bold">Phạm vi demo chủ xưởng</h1><Card>Demo hiện hỗ trợ lịch hẹn, tiếp nhận xe, bắt đầu và hoàn tất dịch vụ, ghi chi phí thực tế và lịch sử trạng thái. Chi phí ước tính và hạng mục được hiển thị trong từng lịch hẹn. Luồng duyệt báo giá và thông báo riêng sẽ được nối ở bước tiếp theo.</Card><Link className="text-emerald" to="/technician">Mở lịch hẹn của xưởng</Link></div>
}
