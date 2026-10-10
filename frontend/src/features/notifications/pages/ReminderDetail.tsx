import { useCallback, useEffect } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getReminderContext } from '../api'
import { reminderActions, RESOLUTION_TEXT } from '../reminderActions'
import { useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { Card } from '@/shared/ui/Card'
import { ErrorState, Notice } from '@/shared/ui/States'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { formatDate, formatKm } from '@/shared/utils/format'

const REASONS = { KM: 'Theo số km', TIME: 'Theo thời gian', BOTH: 'Theo số km và thời gian' }
const DELIVERY_TEXT: Record<string, string> = {
  accepted: 'Nhà cung cấp đã tiếp nhận', delivered: 'Đã giao thư', delayed: 'Giao thư chậm',
  bounced: 'Không giao được thư', complained: 'Người nhận báo spam', suppressed: 'Địa chỉ bị chặn',
  failed: 'Gửi không thành công', pending: 'Đang chờ gửi', cancelled: 'Đã dừng',
  needs_reconciliation: 'Cần kiểm tra lại kết quả gửi',
}

export default function ReminderDetail() {
  const { reminderId = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const fetcher = useCallback(() => getReminderContext(reminderId), [reminderId])
  const query = useCachedQuery(`reminder:${reminderId}`, fetcher, 0)
  const context = query.data
  useEffect(() => {
    if (!context || query.isFetching || query.error) return
    const actions = reminderActions(context)
    const action = params.get('action')
    if (action === 'chat') navigate(actions.chat, { replace: true })
    if (action === 'booking' && actions.booking) navigate(actions.booking, { replace: true })
  }, [context, query.isFetching, query.error, params, navigate])

  if (query.error) return <ErrorState title="Không tải được lời nhắc." traceId={query.error.traceId} onRetry={() => void query.refetch()} />
  if (!context) return <SkeletonCard lines={5} />
  const details = context.details
  const actions = reminderActions(context)
  const current = context.currentStatus.nextMilestone
  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-3xl space-y-5">
      <Link to="/notifications" className="text-sm text-emerald">← Thông báo</Link>
      <h1 className="text-2xl font-bold text-foreground">Lời nhắc bảo dưỡng</h1>
      {context.snapshotAvailable === false && <Notice>Lời nhắc cũ chưa lưu dữ liệu tại thời điểm tạo. Tình trạng hiện tại được hiển thị bên dưới.</Notice>}
      {context.resolved && <Notice>{RESOLUTION_TEXT[context.resolutionReason ?? ''] ?? 'Lời nhắc đã đóng.'}</Notice>}
      <Card className="p-6 space-y-3">
        <h2 className="font-semibold">Dữ liệu dùng cho lời nhắc</h2>
        <p>Mốc {formatKm(context.odoMilestoneKm)}{details.monthMilestone !== null ? ` / ${details.monthMilestone} tháng` : ''}{context.snapshotAvailable !== false ? ` · ${REASONS[details.reason]}` : ''}</p>
        {context.snapshotAvailable !== false && <p className="text-sm text-muted">Hạn theo thời gian: {formatDate(details.dueDate)}.</p>}
        <p className="text-sm text-muted">
          {context.snapshotAvailable === false ? 'Chưa có dữ liệu ODO tại thời điểm tạo lời nhắc.' : details.odometerKm === null ? 'Chưa có ODO; nhắc theo thời gian.' : `ODO: ${formatKm(details.odometerKm)} · cập nhật ${formatDate(details.odometerRecordedAt ?? '')}.`}
        </p>
        {details.odometerStale && <Notice tone="warning">Dữ liệu ODO đã cũ; số km dựa trên lần ghi nhận này.</Notice>}
        <ul className="text-sm text-muted list-disc pl-5 space-y-1">
          {details.items.map(item => <li key={item.itemCode}>{item.itemName}</li>)}
        </ul>
      </Card>
      {context.deliveries.length > 0 && <Card className="p-6 space-y-2">
        <h2 className="font-semibold">Trạng thái gửi lời nhắc</h2>
        {context.deliveries.map(delivery => <p key={delivery.id} className="text-sm text-muted">
          {delivery.mode === 'mock' || delivery.deliveryState === 'mock' ? 'Thư mô phỏng' : delivery.mode === 'resend_test' ? 'Email thử thật [DEMO]' : delivery.channel ?? 'Email'}: {(delivery.mode === 'mock' || delivery.deliveryState === 'mock') && delivery.status === 'SENT' ? 'Đã mô phỏng' : DELIVERY_TEXT[delivery.deliveryState ?? ''] ?? (delivery.status === 'SENT' ? 'Đã tiếp nhận' : 'Chưa hoàn tất')} · {delivery.attempts} lần thử
        </p>)}
      </Card>}
      <Card className="p-6 space-y-3">
        <h2 className="font-semibold">Tình trạng hiện tại</h2>
        <p className="text-sm text-muted">{current ? `Mốc tiếp theo: ${formatKm(current.odoMilestoneKm)} · hạn ${formatDate(current.dueDate)}.` : 'Chưa đủ dữ liệu để xác định mốc hiện tại.'}</p>
        <div className="flex flex-wrap gap-3">
          {actions.booking && <Link to={actions.booking} className="rounded-xl bg-emerald text-white px-4 py-2 text-sm font-semibold">Đặt lịch theo mốc hiện tại</Link>}
          {!actions.booking && (context.hasCurrentBooking || context.resolutionReason === 'HAS_BOOKING') && <Link to="/bookings" className="text-emerald text-sm py-2">Xem lịch hẹn</Link>}
          <Link to={actions.chat} className="rounded-xl border border-border px-4 py-2 text-sm font-semibold text-emerald">Hỏi trợ lý</Link>
        </div>
      </Card>
      <Link to="/notifications/settings#channel-EMAIL" className="text-sm text-emerald">Quản lý / tắt nhận email</Link>
    </div>
  )
}
