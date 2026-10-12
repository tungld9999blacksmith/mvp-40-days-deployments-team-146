import { Link } from 'react-router-dom'
import { formatDate } from '@/shared/utils/format'
import type { MaintenanceForecast } from '../types'

const FALLBACK_TEXT: Record<string, string> = {
  INSUFFICIENT_DATA: 'Chưa đủ lịch sử số km để dự báo.',
  STALE_DATA: 'Số km hãng cập nhật đã cũ, chưa thể dự báo đáng tin cậy.',
  ANOMALOUS_DATA: 'Lịch sử số km có khoảng gián đoạn hoặc giá trị bất thường, chưa thể dự báo.',
  LOW_CONFIDENCE: 'Mức sử dụng xe gần đây thay đổi nhiều, chưa thể dự báo ổn định.',
  UNSUPPORTED_DATA_SOURCE: 'Nguồn số km hiện tại chưa phù hợp để dự báo mức sử dụng.',
  DATA_LIMIT: 'Cần tổng hợp thêm lịch sử số km trước khi dự báo.',
  CALCULATION_ERROR: 'Tạm thời chưa tính được dự báo mức sử dụng.',
}

export default function UsageForecastCard({ forecast, historical = false }: { forecast?: MaintenanceForecast | null; historical?: boolean }) {
  if (!forecast) return null
  if (forecast.status === 'DISABLED') {
    return historical ? null : <p className="text-xs text-muted mt-4"><Link className="text-emerald underline" to="/notifications/settings#personalization">Bật nhắc theo mức sử dụng xe</Link> để dự kiến ngày chạm mốc km.</p>
  }
  if (forecast.status !== 'AVAILABLE' || forecast.avgKmPerDay === null) {
    return <p className="text-sm text-muted mt-4">{FALLBACK_TEXT[forecast.status] ?? 'Chưa thể dự báo mức sử dụng xe.'} Bạn vẫn được nhắc theo mốc km và thời gian.</p>
  }
  return (
    <div className="mt-4 rounded-xl border border-border bg-background p-4 space-y-2">
      <p className="text-sm font-semibold text-foreground">{historical ? 'Mức sử dụng tại lúc tạo lời nhắc' : 'Mức sử dụng xe'}</p>
      <p className="text-sm text-muted">Khoảng <span className="font-semibold text-foreground">{forecast.avgKmPerDay.toLocaleString('vi-VN')} km/ngày</span> trong {Math.round(forecast.observationDays ?? 0)} ngày quan sát.</p>
      {forecast.possiblyReached ? (
        <p className="text-sm text-warning">Xe có thể đã chạm mốc km; cần số ODO mới từ hãng để xác nhận.</p>
      ) : forecast.kmForecastDate ? (
        <p className="text-sm text-muted">Dự kiến chạm mốc km <span className="font-semibold text-foreground">{formatDate(forecast.kmForecastDate)}</span>, nếu duy trì mức sử dụng này.</p>
      ) : (
        <p className="text-sm text-muted">{forecast.avgKmPerDay === 0 ? 'Xe chưa tăng số km trong khoảng quan sát.' : 'Chưa dự báo ngày chạm km trong khoảng 90 ngày.'} Theo dõi hạn bảo dưỡng theo thời gian.</p>
      )}
      {forecast.anchorRecordedAt && <p className="text-xs text-muted">Dựa trên ODO hãng cập nhật ngày {formatDate(forecast.anchorRecordedAt)}. Ngày dự kiến không thay thế hạn bảo dưỡng theo thời gian của hãng.</p>}
      {!historical && forecast.reminderRecommended && <p className="text-sm font-medium text-emerald">Nên lên kế hoạch bảo dưỡng theo mức sử dụng hiện tại.</p>}
    </div>
  )
}
