import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import Button from '@/shared/ui/Button'
import { Notice } from '@/shared/ui/States'
import { setQueryData, useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { formatDate } from '@/shared/utils/format'
import { deleteTripPlan, getTripPlan, saveTripPlan } from '../api'
import { tripBookingLink, validateTrip } from '../tripPlanning'

const inputClass = 'w-full min-w-0 min-h-11 rounded-xl border border-border bg-background p-3 text-foreground focus-field'
const STATUS_TEXT: Record<string, string> = {
  UNKNOWN: 'Chưa đủ dữ liệu hãng để kiểm tra mốc bảo dưỡng cho chuyến đi.',
  ODO_UNAVAILABLE: 'Số km chưa có hoặc đã cũ. Cần dữ liệu hãng mới để đánh giá quãng đường chuyến đi.',
  NO_MILESTONE_CROSSING: 'Theo dữ liệu hiện có, chuyến đi chưa vượt mốc bảo dưỡng tiếp theo. Điều này không thay thế kiểm tra tình trạng xe.',
  DEPARTED: 'Ngày khởi hành đã qua. Bạn có thể khai báo chuyến đi tiếp theo.',
}

export default function TripPlanningCard({ vehicleId }: { vehicleId: string }) {
  const key = `trip:${vehicleId}`
  const fetcher = useCallback(() => getTripPlan(vehicleId), [vehicleId])
  const query = useCachedQuery(key, fetcher, 0)
  const plan = query.data?.plan
  const [departure, setDeparture] = useState('')
  const [returnDate, setReturnDate] = useState('')
  const [distance, setDistance] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setDeparture(plan?.departureDate ?? '')
    setReturnDate(plan?.returnDate ?? '')
    setDistance(plan ? String(plan.distanceKm) : '')
    setEnabled(plan?.reminderEnabled ?? false)
  }, [plan?.updatedAt, vehicleId])
  async function save(event: FormEvent) {
    event.preventDefault()
    const invalid = validateTrip(departure, returnDate, distance)
    if (invalid) { setError(invalid); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      setQueryData(key, await saveTripPlan(vehicleId, { departureDate: departure, returnDate: returnDate || null, distanceKm: Number(distance), reminderEnabled: enabled }))
      setMessage('Đã lưu chuyến đi.')
    } catch { setError('Không lưu được chuyến đi. Kiểm tra ngày khởi hành trong 365 ngày tới rồi thử lại.') }
    finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError(null)
    try { setQueryData(key, await deleteTripPlan(vehicleId)); setMessage('Đã xoá chuyến đi và dừng lượt nhắc đang chờ liên quan.') }
    catch { setError('Không xoá được chuyến đi. Vui lòng thử lại.') }
    finally { setBusy(false) }
  }
  return <Card className="space-y-4">
    <h2 className="text-lg font-semibold text-foreground">Chuẩn bị trước chuyến đi</h2>
    <p className="text-sm text-muted">Khai báo một chuyến đi sắp tới để xem gợi ý bảo dưỡng. Tổng quãng đường gồm cả đi và về; đây là kế hoạch, không ghi vào số km đã chạy của xe.</p>
    {query.error ? <><Notice tone="warning">Không tải được chuyến đi.</Notice><Button variant="secondary" onClick={() => void query.refetch()}>Thử lại</Button></> : <>
      <form onSubmit={save} className="space-y-4">
        <fieldset disabled={busy || query.isFetching} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block text-sm text-muted space-y-2">Ngày khởi hành<input aria-label="Ngày khởi hành" type="date" required value={departure} onChange={e => setDeparture(e.target.value)} className={inputClass} /></label>
            <label className="block text-sm text-muted space-y-2">Ngày về (tuỳ chọn)<input aria-label="Ngày về" type="date" min={departure || undefined} value={returnDate} onChange={e => setReturnDate(e.target.value)} className={inputClass} /></label>
          </div>
          <label className="block text-sm text-muted space-y-2">Tổng quãng đường dự kiến (km)<input aria-label="Tổng quãng đường dự kiến" type="number" min={1} max={20000} step={1} required value={distance} onChange={e => setDistance(e.target.value)} className={inputClass} /></label>
          <label className="flex gap-3 items-start text-sm text-foreground"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="mt-1 accent-emerald" />Nhắc bảo dưỡng trước chuyến đi này qua các kênh tôi đã bật</label>
          <p className="text-xs text-muted">Nhắc dùng số ngày nhắc trước và giờ nhận đã lưu. Bạn vẫn xác nhận đặt lịch; ứng dụng không tự tạo booking. Có thể xoá chuyến đi bất cứ lúc nào.</p>
          <div className="flex flex-wrap gap-3"><Button type="submit" loading={busy}>Lưu chuyến đi</Button>{plan && <Button variant="danger" onClick={() => void remove()} disabled={busy}>Xoá chuyến đi</Button>}</div>
        </fieldset>
      </form>
      {error && <p role="alert" className="text-sm text-error">{error}</p>}
      {message && <p role="status" className="text-sm text-emerald">{message}</p>}
      {plan && <div className="rounded-xl border border-border p-4 space-y-3">
        <p className="text-sm text-muted">Khởi hành {formatDate(plan.departureDate)} · khoảng {plan.distanceKm.toLocaleString('vi-VN')} km.</p>
        {plan.advice.status === 'MAINTENANCE_RECOMMENDED' ? <>
          <p className="text-sm font-semibold text-foreground">Nên lên kế hoạch bảo dưỡng trước chuyến đi{plan.advice.prepareBy ? `, trước ${formatDate(plan.advice.prepareBy)}` : ''}.</p>
          <p className="text-sm text-muted">{plan.advice.reasons.includes('TRIP_KM_MILESTONE') ? 'Quãng đường dự kiến có thể chạm mốc km. ' : ''}{plan.advice.reasons.includes('TRIP_TIME_DEADLINE') ? 'Hạn theo thời gian rơi trước hoặc trong chuyến đi. ' : ''}{plan.advice.reasons.includes('OBSERVED_OVERDUE') ? 'Xe đang quá hạn theo dữ liệu đã ghi nhận.' : ''}</p>
          {plan.advice.projectedTripEndKm !== null && <p className="text-sm text-muted">Số km theo kế hoạch cuối chuyến: khoảng {Math.round(plan.advice.projectedTripEndKm).toLocaleString('vi-VN')} km. Không phải ODO hãng đã xác nhận.</p>}
          {plan.advice.preferredServiceWindow && <p className="text-xs text-muted">Có sở thích đặt lịch đã lưu{plan.advice.preferredServiceWindow.suggestedDate ? `: gợi ý ngày ${formatDate(plan.advice.preferredServiceWindow.suggestedDate)}` : ''}. Xưởng cần xác nhận thời gian còn trống.</p>}
          {plan.advice.preferredWorkshop?.name && <p className="text-xs text-muted">Xưởng ưu tiên: {plan.advice.preferredWorkshop.name}.</p>}
          <Link to={plan.advice.hasBooking ? '/bookings' : tripBookingLink(vehicleId, plan)} className="inline-flex min-h-11 items-center text-sm font-semibold text-emerald underline">{plan.advice.hasBooking ? 'Xem lịch hẹn hiện có' : 'Chọn lịch bảo dưỡng trước chuyến đi'}</Link>
        </> : <p className="text-sm text-muted">{STATUS_TEXT[plan.advice.status]}</p>}
        {plan.reminderEnabled && !plan.advice.reminderActive && <p className="text-xs text-muted">Đã lưu yêu cầu nhận nhắc. Gửi theo chuyến đi sẽ hoạt động khi nhắc tổng bật và tính năng được mở cho tài khoản của bạn.</p>}
      </div>}
    </>}
  </Card>
}
