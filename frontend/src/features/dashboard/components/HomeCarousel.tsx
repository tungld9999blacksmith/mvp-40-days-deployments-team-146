import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Bot, CalendarClock, CalendarPlus, ChevronRight, Wrench } from 'lucide-react'
import Carousel, { type CarouselSlide } from '@/shared/ui/Carousel'
import { cn } from '@/shared/ui/cn'
import { formatLicensePlate, formatNumber } from '@/shared/utils/format'
import { useUpcomingBookings } from '@/features/bookings/hooks/useUpcomingBookings'
import { ASK_AI_QUESTION } from '@/features/vehicles/components/MaintenanceStatusCard'
import { useMaintenanceStatus, useVehicles } from '@/features/vehicles/hooks/useVehicleQueries'
import type { MaintenanceStatus, VehicleSummary } from '@/features/vehicles/types'
import { milestoneTitle, remainingParts } from '@/features/vehicles/utils/maintenanceFormat'
import { homeSlideKinds } from './homeSlides'

const DUE_TAG: Record<string, string> = {
  NORMAL: 'Đúng hạn',
  DUE_SOON: 'Sắp đến hạn',
  OVERDUE: 'Quá hạn',
}

const ASSISTANT_QUESTIONS = [ASK_AI_QUESTION, 'Hạng mục nào được bảo hành miễn phí?', 'Chính sách bảo hành pin thế nào?']

const PRIMARY = 'bg-banner-accent text-banner-on-accent hover:brightness-110'
const GHOST = 'border border-banner-foreground/40 text-banner-foreground hover:bg-banner-foreground/10'

function SlideButton({ to, tone, children }: { to: string; tone: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className={cn('inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all active:scale-[0.98]', tone)}
    >
      {children}
    </Link>
  )
}

/** Instrument-style tag: mono, uppercase, letter-spaced. */
function SlideTag({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 mb-3 font-mono text-[11.5px] font-medium uppercase tracking-[0.06em] text-banner-muted">
      {icon}
      {children}
    </p>
  )
}

function SlideText({ title, body }: { title: string; body: string }) {
  return (
    <>
      <h2 className="text-xl sm:text-[1.7rem] font-extrabold leading-tight tracking-tight text-balance">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed max-w-[52ch] text-banner-muted">{body}</p>
    </>
  )
}

interface Readout {
  label: string
  value: string
  alert: boolean
}

/** Cockpit readouts for the due status, straight from backend numbers. */
function readouts(status: MaintenanceStatus): Readout[] {
  const alerting = status.dueStatus === 'DUE_SOON' || status.dueStatus === 'OVERDUE'
  const kmAlert = alerting && (status.dueReason === 'KM' || status.dueReason === 'BOTH')
  const dayAlert = alerting && (status.dueReason === 'TIME' || status.dueReason === 'BOTH')
  const cells: Readout[] = []
  const { remainingKm: km, remainingDays: days } = status
  if (km !== null) cells.push({ label: km >= 0 ? 'Còn lại' : 'Quá mốc', value: `${formatNumber(Math.abs(km))} km`, alert: kmAlert })
  if (days !== null) cells.push({ label: days >= 0 ? 'Thời gian' : 'Quá hạn', value: `${formatNumber(Math.abs(days))} ngày`, alert: dayAlert })
  if (cells.length < 2 && status.nextMilestone) {
    cells.push({ label: 'Mốc', value: `${formatNumber(status.nextMilestone.odoMilestoneKm)} km`, alert: false })
  }
  return cells
}

function ReadoutGrid({ cells }: { cells: Readout[] }) {
  return (
    // Below sm the headline already reads "còn 600 km · 12 ngày"; the readouts only add height.
    <div className="hidden sm:grid grid-cols-2 rounded-2xl border border-banner-border md:w-full md:max-w-xs md:justify-self-end">
      {cells.slice(0, 2).map((cell, i) => (
        <div key={cell.label} className={cn('px-4 py-3', i > 0 && 'border-l border-banner-border')}>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-banner-muted">{cell.label}</p>
          <p className={cn('mt-1 font-plate text-[2.15rem] font-bold leading-none', cell.alert && 'text-amber-400')}>{cell.value}</p>
        </div>
      ))}
    </div>
  )
}

function MaintenanceSlide({ vehicle, status }: { vehicle: VehicleSummary; status: MaintenanceStatus }) {
  const milestone = status.nextMilestone!
  const remaining = remainingParts(status).map(part => part.text).join(' · ')
  const model = [vehicle.modelName, vehicle.trim].filter(Boolean).join(' ')
  const tag = [DUE_TAG[status.dueStatus] ?? 'Bảo dưỡng', model, formatLicensePlate(vehicle.licensePlate)].filter(Boolean).join(' · ')

  return (
    <div className="grid gap-6 md:grid-cols-[1.3fr_1fr] md:items-center">
      <div className="min-w-0">
        <SlideTag icon={<Wrench className="w-3.5 h-3.5" aria-hidden />}>{tag}</SlideTag>
        <SlideText
          title={remaining ? `${milestoneTitle(milestone)}: ${remaining.charAt(0).toLowerCase()}${remaining.slice(1)}` : milestoneTitle(milestone)}
          body="Xem chi phí dự kiến cho gói tiêu chuẩn, rồi chọn khung giờ trống tại xưởng gần bạn."
        />
        <div className="mt-5 flex flex-wrap gap-2.5">
          <SlideButton to="/booking" tone={PRIMARY}>
            <CalendarPlus className="w-4 h-4" aria-hidden />
            Đặt lịch bảo dưỡng
          </SlideButton>
          <SlideButton to={`/estimate?odoMilestone=${milestone.odoMilestoneKm}`} tone={GHOST}>
            Xem chi phí dự kiến
          </SlideButton>
        </div>
      </div>
      <ReadoutGrid cells={readouts(status)} />
    </div>
  )
}

function BookingSlide() {
  return (
    <div className="grid gap-6 md:grid-cols-[1.3fr_1fr] md:items-center">
      <div className="min-w-0">
        <SlideTag icon={<CalendarClock className="w-3.5 h-3.5" aria-hidden />}>Đặt lịch</SlideTag>
        <SlideText
          title="Chọn xưởng gần bạn, giữ chỗ trong vài chạm"
          body="Xem khung giờ trống của các xưởng VinFast quanh bạn. Xưởng xác nhận lịch ngay trong ứng dụng."
        />
        <div className="mt-5">
          <SlideButton to="/booking" tone={PRIMARY}>
            <CalendarPlus className="w-4 h-4" aria-hidden />
            Đặt lịch ngay
          </SlideButton>
        </div>
      </div>
      <CalendarClock className="hidden md:block w-24 h-24 justify-self-end text-banner-accent/35" strokeWidth={1.25} aria-hidden />
    </div>
  )
}

function AssistantSlide() {
  return (
    <div className="grid gap-6 md:grid-cols-[1.3fr_1fr] md:items-center">
      <div className="min-w-0">
        <SlideTag icon={<Bot className="w-3.5 h-3.5" aria-hidden />}>AI Trợ lý</SlideTag>
        <SlideText
          title="Không chắc hạng mục nào cần làm?"
          body="Hỏi trợ lý AI. Câu trả lời trích nguồn từ tài liệu chính hãng cho đúng mẫu xe của bạn."
        />
        <div className="mt-5">
          <SlideButton to="/ai" tone={PRIMARY}>
            <Bot className="w-4 h-4" aria-hidden />
            Hỏi trợ lý ngay
          </SlideButton>
        </div>
      </div>
      {/* Hidden on phones: the AI card further down the same page lists these questions. */}
      <div className="hidden sm:grid gap-2 md:max-w-xs md:w-full md:justify-self-end">
        {ASSISTANT_QUESTIONS.map(question => (
          <Link
            key={question}
            to={`/ai?q=${encodeURIComponent(question)}`}
            className="group flex items-center justify-between gap-3 rounded-xl border border-banner-border px-3.5 py-2.5 text-sm text-banner-foreground hover:bg-banner-foreground/5 transition-colors"
          >
            {question}
            <ChevronRight className="w-4 h-4 text-banner-muted shrink-0 group-hover:translate-x-0.5 group-hover:text-banner-accent transition-transform" aria-hidden />
          </Link>
        ))}
      </div>
    </div>
  )
}

/** Home banner (top of Dashboard): due status, booking, assistant. Built only from real data and real features. */
export default function HomeCarousel() {
  const vehicles = useVehicles()
  const vehicle = vehicles.data?.[0] ?? null
  const status = useMaintenanceStatus(vehicle?.userVehicleId ?? null)
  const upcoming = useUpcomingBookings()
  const hasUpcomingBooking = (upcoming.data?.items.length ?? 0) > 0

  const kinds = homeSlideKinds({ status: vehicle ? status.data : null, hasUpcomingBooking })
  const slides: CarouselSlide[] = kinds.map(kind => {
    if (kind === 'maintenance' && vehicle && status.data) {
      return { id: kind, label: 'Hạn bảo dưỡng', content: <MaintenanceSlide vehicle={vehicle} status={status.data} /> }
    }
    if (kind === 'booking') return { id: kind, label: 'Đặt lịch', content: <BookingSlide /> }
    return { id: 'assistant', label: 'AI Trợ lý', content: <AssistantSlide /> }
  })

  return <Carousel slides={slides} label="Thông tin nổi bật" className="mb-6" />
}
