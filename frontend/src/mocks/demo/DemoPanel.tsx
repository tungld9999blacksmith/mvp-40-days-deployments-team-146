import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeftRight,
  Car,
  Check,
  ChevronRight,
  ClipboardList,
  Copy,
  FastForward,
  Play,
  RotateCcw,
  SkipForward,
  Store,
  X,
} from 'lucide-react'
import { MOCK_CHAT_STORAGE_KEY } from '@/features/assistant/transport/mockStore'
import { demoSignIn, demoSignOut } from '@/features/auth/demoAuth'
import { clearPortal, setPortal, type Portal } from '@/features/auth/portal'
import { clearSessionCaches } from '@/shared/session/sessionCache'
import Button from '@/shared/ui/Button'
import { cn } from '@/shared/ui/cn'
import {
  DEMO_SAMPLE,
  demoProgress,
  openFollowUpNow,
  resetDemo,
  restartWorkshopOnboarding,
  skipOwnerOnboarding,
  type DemoProgress,
} from '@/mocks/server/demo'

/**
 * Floating guide of demo mode (`npm run dev:demo`): the scripted end-to-end flow with its live
 * progress read from the mock data, sample input for the forms, and shortcuts (skip onboarding,
 * switch portal, open the survey now, start over). Never rendered outside demo mode.
 */

const OPEN_KEY = 'evcare.demo.panelOpen'
const VISITED_KEY = 'evcare.demo.visited'
const REFRESH_MS = 1_500

const SUGGESTED_QUESTIONS = [
  'Mốc bảo dưỡng tới của xe gồm những hạng mục nào?',
  'Chi phí bảo dưỡng mốc tới khoảng bao nhiêu?',
  'Sạc pin thế nào cho bền?',
  'Đặt lịch bảo dưỡng giúp tôi',
]

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // storage blocked: the panel just forgets
  }
}

function readVisited(): string[] {
  try {
    const parsed: unknown = JSON.parse(readStorage(VISITED_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

/** Screens whose visit completes a step (they change no data). */
function visitKey(pathname: string): string | null {
  if (pathname === '/dashboard') return 'dashboard'
  if (pathname.startsWith('/ai')) return 'ai'
  if (pathname.startsWith('/estimate')) return 'estimate'
  return null
}

function isLoginScreen(pathname: string): boolean {
  return pathname === '/' || pathname.startsWith('/workshop/login')
}

/** Sign-in and onboarding screens keep their form on the right: the panel moves left there. */
function isAuthScreen(pathname: string): boolean {
  return pathname === '/' || pathname.startsWith('/onboarding') || pathname.startsWith('/workshop/login') || pathname.startsWith('/workshop/onboarding')
}

/** Corner of the panel: left on auth screens, above the full-width chat composer of small screens, else bottom right. */
function placement(pathname: string): string {
  if (isAuthScreen(pathname)) return 'left-4 bottom-4'
  return pathname.startsWith('/ai') ? 'right-4 bottom-28 lg:bottom-4' : 'right-4 bottom-4'
}

function portalOf(pathname: string): Portal {
  return pathname.startsWith('/technician') || pathname.startsWith('/workshop') ? 'workshop' : 'owner'
}

interface Step {
  id: string
  portal: Portal
  title: string
  hint: ReactNode
  to: string
  done: boolean
}

function buildSteps(progress: DemoProgress | null, visited: string[]): Step[] {
  const booking = progress?.booking ?? null
  const reached = (state: Parameters<NonNullable<DemoProgress['booking']>['reached']>[0]) => Boolean(booking?.reached(state))
  const boardPath = booking ? `/technician/board/${encodeURIComponent(booking.bookingId)}` : '/technician/board'
  const followUp = progress?.followUp ?? null
  return [
    {
      id: 'onboard',
      portal: 'owner',
      title: 'Đăng nhập & xác thực xe',
      hint: 'Google (demo) → thông tin cá nhân → VIN, biển số → hãng xác thực. Dữ liệu mẫu ở tab bên cạnh.',
      to: '/',
      done: Boolean(progress?.ownerActive),
    },
    {
      id: 'status',
      portal: 'owner',
      title: 'Xem hạn bảo dưỡng',
      hint: 'Trang chủ: mốc kế tiếp, số km / ngày còn lại và các hạng mục.',
      to: '/dashboard',
      done: visited.includes('dashboard'),
    },
    {
      id: 'ai',
      portal: 'owner',
      title: 'Hỏi trợ lý AI',
      hint: 'Hỏi về mốc bảo dưỡng (có trích nguồn), hỏi chi phí (thẻ dự toán), thử ô "Đặt lịch bảo dưỡng nhanh".',
      to: '/ai',
      done: visited.includes('ai'),
    },
    {
      id: 'estimate',
      portal: 'owner',
      title: 'Xem dự toán chi phí',
      hint: 'Chi phí theo mốc và xưởng; so sánh 2–3 xưởng.',
      to: '/estimate',
      done: visited.includes('estimate'),
    },
    {
      id: 'book',
      portal: 'owner',
      title: 'Đặt lịch hẹn',
      hint: 'Chọn xưởng → ngày & giờ → Xác nhận. Hoặc bấm "Xác nhận đặt lịch" trên thẻ đề xuất của trợ lý.',
      to: '/booking',
      done: booking !== null,
    },
    {
      id: 'accept',
      portal: 'workshop',
      title: 'Xưởng xác nhận lịch',
      hint: 'Workshop Portal → Board: mở lịch "Chờ xác nhận" → Chấp nhận. (Xưởng ở chế độ AUTO thì lịch được xác nhận ngay.)',
      to: boardPath,
      done: reached('confirmed'),
    },
    {
      id: 'checkin',
      portal: 'workshop',
      title: 'Check-in khi khách tới',
      hint: booking?.code ? (
        <>
          Nhập mã <CopyValue value={booking.code} /> (trên vé của chủ xe) hoặc quét QR.
        </>
      ) : (
        'Nhập mã EVC-… trên vé của chủ xe hoặc quét QR.'
      ),
      to: booking?.code ? `/technician/check-in?code=${encodeURIComponent(booking.code)}` : '/technician/check-in',
      done: reached('checked_in'),
    },
    {
      id: 'service',
      portal: 'workshop',
      title: 'Cập nhật tiến độ & hoàn tất',
      hint: 'Bắt đầu → Đang bảo dưỡng → Kiểm tra chất lượng → Sẵn sàng giao xe → Hoàn tất (nhập chi phí thực tế).',
      to: boardPath,
      done: reached('completed'),
    },
    {
      id: 'review',
      portal: 'owner',
      title: 'Chủ xe theo dõi & đánh giá',
      hint: 'Vé lịch hẹn hiện tiến độ 6 bước; sau khi hoàn tất, khảo sát mở trong mục Thông báo (sau 1 phút).',
      to: followUp?.open ? `/follow-ups/${encodeURIComponent(followUp.followUpId)}` : booking ? `/bookings/${encodeURIComponent(booking.bookingId)}` : '/bookings',
      done: Boolean(followUp?.responded),
    },
  ]
}

function copyText(value: string) {
  void navigator.clipboard?.writeText(value).catch(() => {})
}

function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={event => {
        event.stopPropagation()
        copyText(value)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1_200)
      }}
      className="inline-flex items-center gap-1 rounded-md bg-foreground/5 px-1.5 py-0.5 font-mono text-[11px] text-foreground hover:bg-foreground/10"
      title="Chép"
    >
      {value}
      {copied ? <Check className="h-3 w-3 text-emerald" aria-label="Đã chép" /> : <Copy className="h-3 w-3 text-muted" aria-hidden />}
    </button>
  )
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-xs text-muted">{label}</span>
      <CopyValue value={value} />
    </div>
  )
}

function DataSection({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="space-y-1">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
        {icon}
        {title}
      </p>
      <div className="rounded-xl border border-border px-3 py-1.5">{children}</div>
    </section>
  )
}

function SampleData() {
  const { owner, vehicle, failingVin, workshopOwner } = DEMO_SAMPLE
  return (
    <div className="space-y-4">
      <DataSection icon={<ClipboardList className="h-3.5 w-3.5" />} title="Thông tin chủ xe">
        <DataRow label="Họ tên" value={owner.fullName} />
        <DataRow label="Số điện thoại" value={owner.phoneNumber} />
        <DataRow label="CCCD" value={owner.nationalId} />
        <DataRow label="Ngày sinh" value={owner.dateOfBirth.split('-').reverse().join('/')} />
        <DataRow label="Địa chỉ" value={owner.addressLine} />
        <DataRow label="Tỉnh/TP" value={owner.province} />
      </DataSection>
      <DataSection icon={<Car className="h-3.5 w-3.5" />} title="Xe">
        <DataRow label="Số VIN" value={vehicle.vin} />
        <DataRow label="Biển số" value={vehicle.licensePlate} />
        <DataRow label="Mẫu xe" value={vehicle.modelLabel} />
        <DataRow label="Năm sản xuất" value={String(vehicle.manufactureYear)} />
        <DataRow label="VIN bị hãng từ chối" value={failingVin} />
      </DataSection>
      <DataSection icon={<Store className="h-3.5 w-3.5" />} title="Chủ xưởng (onboarding xưởng)">
        <DataRow label="Họ tên" value={workshopOwner.fullName} />
        <DataRow label="Số điện thoại" value={workshopOwner.phoneNumber} />
        <DataRow label="CCCD" value={workshopOwner.nationalId} />
        <DataRow label="Hotline" value={workshopOwner.hotline} />
      </DataSection>
      <DataSection icon={<Play className="h-3.5 w-3.5" />} title="Câu hỏi gợi ý cho trợ lý">
        {SUGGESTED_QUESTIONS.map(question => (
          <button
            key={question}
            type="button"
            onClick={() => copyText(question)}
            className="block w-full py-1 text-left text-xs text-foreground/80 hover:text-emerald"
            title="Chép câu hỏi"
          >
            “{question}”
          </button>
        ))}
      </DataSection>
    </div>
  )
}

export default function DemoPanel() {
  const location = useLocation()
  const navigate = useNavigate()
  // First visit on a login page starts collapsed so the brand panel is seen first; afterwards the
  // viewer's own choice wins.
  const [open, setOpen] = useState(() => {
    const stored = readStorage(OPEN_KEY)
    return stored === null ? !isLoginScreen(location.pathname) : stored !== '0'
  })
  const [tab, setTab] = useState<'flow' | 'data'>('flow')
  const [visited, setVisited] = useState<string[]>(readVisited)
  const [progress, setProgress] = useState<DemoProgress | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [busy, setBusy] = useState(false)
  const portal = portalOf(location.pathname)

  useEffect(() => {
    const key = visitKey(location.pathname)
    if (!key) return
    setVisited(current => {
      if (current.includes(key)) return current
      const next = [...current, key]
      writeStorage(VISITED_KEY, JSON.stringify(next))
      return next
    })
  }, [location.pathname])

  useEffect(() => {
    const tick = () => setProgress(demoProgress())
    tick()
    const timer = window.setInterval(tick, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [])

  const steps = useMemo(() => buildSteps(progress, visited), [progress, visited])
  const doneCount = steps.filter(step => step.done).length
  const current = steps.find(step => !step.done) ?? null

  const toggle = (value: boolean) => {
    setOpen(value)
    writeStorage(OPEN_KEY, value ? '1' : '0')
  }

  /**
   * Opens a step and folds the panel so the screen stays clear. Same tab, other portal: drop the
   * cached screens so the other side's changes show.
   */
  const go = (to: string, target: Portal) => {
    if (target !== portal) clearSessionCaches()
    setPortal(target)
    toggle(false)
    navigate(to)
  }

  async function skipOnboarding() {
    setBusy(true)
    skipOwnerOnboarding()
    await demoSignIn()
    setPortal('owner')
    window.location.assign('/dashboard')
  }

  function replayWorkshopOnboarding() {
    restartWorkshopOnboarding()
    setPortal('workshop')
    window.location.assign('/technician')
  }

  async function startOver() {
    setBusy(true)
    resetDemo()
    await demoSignOut()
    clearPortal()
    writeStorage(VISITED_KEY, null)
    writeStorage(MOCK_CHAT_STORAGE_KEY, null)
    window.location.assign('/')
  }

  const booking = progress?.booking ?? null
  const surveyPending = Boolean(booking?.reached('completed') && progress?.followUp && !progress.followUp.open)

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => toggle(true)}
        className={cn(
          'fixed z-40 inline-flex items-center gap-2 rounded-full bg-brand-gradient px-4 py-2.5 text-sm font-semibold text-on-brand shadow-lg glow-emerald',
          placement(location.pathname),
        )}
        aria-label="Mở hướng dẫn demo"
      >
        <Play className="h-4 w-4 flex-shrink-0" aria-hidden />
        <span>Demo · {doneCount}/{steps.length}</span>
        {current && <span className="hidden max-w-56 truncate font-normal opacity-80 sm:inline">— {current.title}</span>}
      </button>
    )
  }

  return (
    <aside
      className={cn(
        'fixed z-40 flex max-h-[min(40rem,calc(100vh-9rem))] w-[min(22rem,calc(100vw-2rem))] flex-col rounded-2xl border border-border bg-card shadow-2xl elevation-md',
        placement(location.pathname),
      )}
      aria-label="Hướng dẫn demo"
    >
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-gradient">
          <Play className="h-3.5 w-3.5 text-on-brand" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground">Kịch bản demo</p>
          <p className="text-[11px] text-muted">
            {doneCount}/{steps.length} bước · đang ở {portal === 'workshop' ? 'Workshop Portal' : 'app chủ xe'}
          </p>
        </div>
        <button type="button" onClick={() => toggle(false)} className="rounded-lg p-1.5 text-muted hover:bg-foreground/5 hover:text-foreground" aria-label="Thu gọn">
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex gap-1 px-4 pt-3" role="tablist">
        {(['flow', 'data'] as const).map(value => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              'flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
              tab === value ? 'bg-emerald/10 text-emerald' : 'text-muted hover:text-foreground',
            )}
          >
            {value === 'flow' ? 'Luồng end-to-end' : 'Dữ liệu mẫu'}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {tab === 'data' ? (
          <SampleData />
        ) : (
          <ol className="space-y-1">
            {steps.map((step, index) => {
              const isCurrent = step === current
              return (
                <li key={step.id} className={cn('rounded-xl', isCurrent && 'bg-emerald/10 ring-1 ring-inset ring-emerald/25')}>
                  <button
                    type="button"
                    onClick={() => go(step.to, step.portal)}
                    className={cn(
                      'group flex w-full items-start gap-3 rounded-xl px-2.5 py-1.5 text-left transition-colors',
                      !isCurrent && 'hover:bg-foreground/5',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                        step.done ? 'bg-brand text-on-brand' : isCurrent ? 'ring-1 ring-emerald text-emerald' : 'ring-1 ring-border text-muted',
                      )}
                    >
                      {step.done ? <Check className="h-3 w-3" aria-label="Xong" /> : index + 1}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-1.5 gap-y-0.5">
                      <span className={cn('text-sm font-medium', step.done ? 'text-muted' : 'text-foreground')}>{step.title}</span>
                      <span className="whitespace-nowrap rounded-full bg-foreground/5 px-1.5 py-px text-[10px] text-muted">
                        {step.portal === 'workshop' ? 'Xưởng' : 'Chủ xe'}
                      </span>
                    </span>
                    <ChevronRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                  </button>
                  {/* Outside the button: the hint may hold its own copy button. */}
                  {isCurrent && <div className="pb-2 pl-10 pr-3 text-xs leading-relaxed text-muted">{step.hint}</div>}
                </li>
              )
            })}
          </ol>
        )}
      </div>

      <footer className="space-y-2 border-t border-border px-4 py-3">
        <div className="flex flex-wrap gap-2">
          {!progress?.ownerActive && (
            <Button size="sm" variant="secondary" icon={<SkipForward className="h-3.5 w-3.5" />} onClick={() => void skipOnboarding()} disabled={busy}>
              Bỏ qua onboarding
            </Button>
          )}
          {surveyPending && booking && (
            <Button size="sm" variant="secondary" icon={<FastForward className="h-3.5 w-3.5" />} onClick={() => openFollowUpNow(booking.bookingId)}>
              Mở khảo sát ngay
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            icon={<ArrowLeftRight className="h-3.5 w-3.5" />}
            onClick={() => (portal === 'workshop' ? go('/dashboard', 'owner') : go('/technician', 'workshop'))}
          >
            {portal === 'workshop' ? 'Sang app chủ xe' : 'Sang Workshop Portal'}
          </Button>
          <Button size="sm" variant="ghost" onClick={replayWorkshopOnboarding} disabled={busy}>
            Onboarding xưởng
          </Button>
          <Button
            size="sm"
            variant={confirmReset ? 'danger' : 'ghost'}
            icon={<RotateCcw className="h-3.5 w-3.5" />}
            onClick={() => (confirmReset ? void startOver() : setConfirmReset(true))}
            onBlur={() => setConfirmReset(false)}
            disabled={busy}
          >
            {confirmReset ? 'Bấm lần nữa để xoá dữ liệu' : 'Làm lại từ đầu'}
          </Button>
        </div>
        <p className="text-[11px] leading-relaxed text-muted">
          Dữ liệu giả, lưu trong trình duyệt này. Có thể mở app chủ xe và Workshop Portal ở hai tab cạnh nhau. Demo cho phép check-in trước ngày hẹn; khảo sát mở 1 phút sau khi hoàn tất.
        </p>
      </footer>
    </aside>
  )
}
