import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getDemoEmailOutbox, NOTIFICATION_FEED_KEY, runDemoReminders, sendDemoTestEmail } from '../api'
import { invalidateQuery, useCachedQuery } from '@/shared/hooks/useCachedQuery'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { page } from '@/shared/ui/page'

export default function DemoEmailOutbox() {
  const query = useCachedQuery('demo-email-outbox', getDemoEmailOutbox, 0)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const realTest = query.data?.mode === 'resend_test'
  async function scan(sendReal = false) {
    setBusy(true)
    try {
      if (sendReal) await sendDemoTestEmail()
      else await runDemoReminders()
      invalidateQuery(NOTIFICATION_FEED_KEY)
      await query.refetch()
      toast.show(sendReal ? 'Đã kiểm tra yêu cầu gửi thử. Xem trạng thái bên dưới.' : 'Đã kiểm tra mốc bảo dưỡng.', 'success')
    } catch (error) {
      toast.show(isApiError(error) ? error.message : 'Không kiểm tra được lời nhắc.', 'error')
    } finally { setBusy(false) }
  }
  if (query.data && !['mock', 'resend_test'].includes(query.data.mode)) return (
    <div className={`${page('reading')} space-y-4`}>
      <Link to="/notifications" className="text-sm text-emerald">← Thông báo</Link>
      <Notice>Hộp thư mô phỏng chỉ có khi ứng dụng dùng email mock. Xem trạng thái gửi thật trong chi tiết lời nhắc.</Notice>
    </div>
  )
  return (
    <div className={`${page('reading')} space-y-5`}>
      <Link to="/notifications/settings" className="text-sm text-emerald">← Cài đặt nhắc bảo dưỡng</Link>
      <h1 className="text-2xl font-bold text-foreground">Hộp thư demo</h1>
      <Notice>{realTest
        ? 'Thư gửi thật qua Resend đến địa chỉ thử đã cấu hình. Nội dung xe và mốc bảo dưỡng là dữ liệu demo. Chỉ gửi khi bấm nút; địa chỉ thử nhận tối đa một email nhắc mới trong 7 ngày.'
        : 'Thư trong hộp này mô phỏng gửi email. Chưa gửi đến hộp thư thật. Mỗi xe chỉ nhận tối đa một email nhắc mới trong 7 ngày.'}</Notice>
      {query.data?.mode === 'mock' && query.data.canRunReminders === true && <Button onClick={() => void scan()} loading={busy}>Kiểm tra mốc ngay</Button>}
      {realTest && query.data?.canSendTestEmail === true && <Button onClick={() => void scan(true)} loading={busy}>Gửi thử email thật</Button>}
      {realTest && query.data?.canSendTestEmail !== true && <Notice>Tài khoản demo cần dùng email trùng địa chỉ gửi thử đã cấu hình.</Notice>}
      {query.error ? <ErrorState title="Chưa tải được hộp thư demo." onRetry={() => void query.refetch()} />
        : !query.data ? <p className="text-sm text-muted">Đang tải…</p>
        : !query.data.items.length ? <EmptyState title={realTest ? 'Chưa gửi email thử' : 'Chưa có email mô phỏng'} description={`Bật nhắc bảo dưỡng và Email, rồi ${realTest ? 'bấm Gửi thử email thật' : 'kiểm tra mốc'}. Thư được tạo khi xe chạm ngưỡng nhắc, chưa có lịch hẹn đúng mốc và chưa bị giới hạn tần suất.`} />
        : query.data.items.map(email => (
          <Card key={email.id} className="p-5 space-y-3">
            <h2 className="font-semibold">{email.payload.subject}</h2>
            <p className="text-xs text-muted">{realTest
              ? email.deliveryState === 'delivered' ? 'Đã giao thư' : email.status === 'SENT' ? 'Resend đã tiếp nhận' : 'Gửi chưa thành công'
              : email.status === 'SENT' ? 'Đã tạo thư mô phỏng' : 'Chưa hoàn tất'} · {email.attempts} lần thử</p>
            {email.errorCode && <p className="text-sm text-error">{email.errorCode === 'DELIVERY_FORBIDDEN'
              ? 'Resend từ chối gửi. Kiểm tra key, người gửi và địa chỉ nhận được phép.'
              : email.errorCode === 'RECONCILIATION_REQUIRED' ? 'Cần đối chiếu kết quả gửi trên Resend trước khi thử thêm.'
              : 'Chưa gửi được thư. Kiểm tra chi tiết lời nhắc và thử lại khi đủ điều kiện.'}</p>}
            <iframe title={`Email ${email.id}`} srcDoc={email.payload.html} sandbox="" className="w-full h-[28rem] bg-white rounded-xl border border-border" />
            <Link className="inline-block text-sm font-semibold text-emerald" to={`/notifications/reminders/${encodeURIComponent(email.reminderId)}`}>Xem lời nhắc và hành động</Link>
            <details><summary className="text-xs text-muted cursor-pointer">Bản văn bản thuần</summary><pre className="text-xs whitespace-pre-wrap break-words mt-2">{email.payload.body}</pre></details>
          </Card>
        ))}
    </div>
  )
}
