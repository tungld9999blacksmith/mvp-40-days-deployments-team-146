import { useEffect, useRef, type ReactNode } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ChevronRight, MapPin, MessageSquare } from 'lucide-react'
import { track } from '@/shared/utils/track'
import { useBookingWizard, type BookingParams } from '../context/BookingWizardContext'

function entryOf(params: BookingParams): 'HOME' | 'ESTIMATE' | 'QUOTE' | 'MENU' {
  if (params.quoteId) return 'QUOTE'
  if (params.workshopId) return 'ESTIMATE'
  if (params.odoMilestone !== null) return 'HOME'
  return 'MENU'
}

function Choice({
  icon,
  title,
  description,
  onClick,
}: {
  icon: ReactNode
  title: string
  description: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-card border border-border rounded-2xl p-5 flex items-center gap-4 hover:bg-card-hover hover:border-emerald/40 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald/40"
    >
      <span className="w-11 h-11 rounded-xl bg-emerald/10 text-emerald flex items-center justify-center shrink-0">{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-semibold text-foreground">{title}</span>
        <span className="block text-sm text-muted mt-0.5">{description}</span>
      </span>
      <ChevronRight className="w-4 h-4 text-muted shrink-0" />
    </button>
  )
}

/** SCR-401 — choose chat or self-service booking. Skipped when a workshop is already known. */
export default function BookingStart() {
  const navigate = useNavigate()
  const { params, searchFor } = useBookingWizard()

  const entry = useRef(entryOf(params)).current
  useEffect(() => {
    track('booking_started', { entry })
  }, [entry])

  if (params.workshopId) return <Navigate to={`/booking/slots${searchFor({})}`} replace />

  return (
    <div className="max-w-2xl space-y-3">
      <p className="text-sm text-muted mb-2">Bạn muốn đặt lịch theo cách nào?</p>
      <Choice
        icon={<MapPin className="w-5 h-5" />}
        title="Tự chọn xưởng & giờ"
        description="Xem xưởng gần bạn, khung giờ còn chỗ và xác nhận ngay."
        onClick={() => navigate(`/booking/workshops${searchFor({})}`)}
      />
      <Choice
        icon={<MessageSquare className="w-5 h-5" />}
        title="Đặt qua trò chuyện"
        description="Nói với Trợ lý AI thời gian và nơi bạn muốn, trợ lý sẽ gợi ý giúp."
        onClick={() => navigate('/ai/new')}
      />
    </div>
  )
}
