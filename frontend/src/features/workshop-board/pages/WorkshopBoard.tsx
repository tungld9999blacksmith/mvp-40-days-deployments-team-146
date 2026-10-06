import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CalendarDays, CheckCircle2, LogIn, Play, QrCode, Search, Settings2 } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Drawer from '@/shared/ui/Drawer'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState, Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { cn } from '@/shared/ui/cn'
import { bookingStatusLabel, PORTAL_BOOKING_STATUS as BOOKING_STATUS } from '@/shared/domain/bookingLabels'
import { formatLicensePlate } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { addDays, formatLongDay, slotLabel, todayVn } from '@/features/bookings/utils'
import { getBoard, getBoardBooking, transitionBooking } from '../api'
import BoardBookingDetail, { DeadlineBadge } from '../components/BoardBookingDetail'
import type { BoardAction, BoardData, BoardDetail, BoardItem, BoardStatus, TransitionResult } from '../types'

const STATUSES: BoardStatus[] = ['PENDING', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']
const QUICK: { action: BoardAction; label: string; icon: typeof CheckCircle2 }[] = [
  { action: 'ACCEPT', label: 'Chấp nhận', icon: CheckCircle2 },
  { action: 'CHECK_IN', label: 'Check-in', icon: LogIn },
  { action: 'START', label: 'Bắt đầu', icon: Play },
]
const REFRESH_MS = 60_000
const SUCCESS: Partial<Record<BoardAction, string>> = {
  ACCEPT: 'Đã chấp nhận lịch hẹn.',
  REJECT: 'Đã từ chối yêu cầu.',
  CHECK_IN: 'Đã check-in.',
  START: 'Đã bắt đầu làm.',
  COMPLETE: 'Đã hoàn tất dịch vụ.',
  CANCEL: 'Đã huỷ lịch hẹn.',
}

type Range = 'today' | 'week' | 'day'

function useBoardQuery() {
  const [searchParams, setSearchParams] = useSearchParams()
  const today = todayVn()
  const from = searchParams.get('from') ?? today
  const to = searchParams.get('to') ?? from
  const statuses = searchParams.getAll('status').filter((item): item is BoardStatus => STATUSES.includes(item as BoardStatus))
  const q = searchParams.get('q') ?? ''
  const range: Range = from === today && to === today ? 'today' : from === today && to === addDays(today, 6) ? 'week' : 'day'
  const update = useCallback(
    (patch: { from?: string; to?: string; statuses?: BoardStatus[]; q?: string }) => {
      setSearchParams(
        current => {
          const next = new URLSearchParams(current)
          if (patch.from !== undefined) next.set('from', patch.from)
          if (patch.to !== undefined) next.set('to', patch.to)
          if (patch.statuses !== undefined) {
            next.delete('status')
            patch.statuses.forEach(status => next.append('status', status))
          }
          if (patch.q !== undefined) {
            if (patch.q) next.set('q', patch.q)
            else next.delete('q')
          }
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )
  return { from, to, statuses, q, range, update, search: searchParams.toString() }
}

function emptyText(range: Range): string {
  return range === 'today' ? 'Chưa có lịch hẹn nào hôm nay.' : range === 'week' ? 'Chưa có lịch hẹn nào trong 7 ngày tới.' : 'Chưa có lịch hẹn nào trong ngày này.'
}

/** SCR-801 + drawer SCR-802 — Workshop Board (`/technician/board[/:bookingId]`). */
export default function WorkshopBoard() {
  const navigate = useNavigate()
  const toast = useToast()
  const { bookingId } = useParams()
  const { from, to, statuses, q, range, update, search } = useBoardQuery()
  const [data, setData] = useState<BoardData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [staleError, setStaleError] = useState(false)
  const [pending, setPending] = useState<{ bookingId: string; action: BoardAction } | null>(null)
  const [detail, setDetail] = useState<BoardDetail | null>(null)
  const [detailError, setDetailError] = useState<ApiError | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [progressKey, setProgressKey] = useState(0)
  const [inactive, setInactive] = useState(false)
  const [searchText, setSearchText] = useState(q)
  const controller = useRef<AbortController | null>(null)
  const viewed = useRef(false)

  const load = useCallback(
    async (background = false) => {
      controller.current?.abort()
      const current = new AbortController()
      controller.current = current
      if (background) setRefreshing(true)
      try {
        const result = await getBoard({ from, to, statuses, q: q.length >= 2 ? q : '', signal: current.signal })
        setData(result)
        setError(null)
        setStaleError(false)
        if (!viewed.current) {
          viewed.current = true
          track('board_viewed', { range, statusFilterCount: statuses.length })
        }
      } catch (reason) {
        if (current.signal.aborted) return
        if (background) setStaleError(true)
        else setError(isApiError(reason) ? reason : null)
      } finally {
        if (background) setRefreshing(false)
      }
    },
    // `statuses` is derived from the query string (`search`).
    [from, to, q, search],
  )

  useEffect(() => {
    setData(null)
    void load()
  }, [load])

  // Auto refresh every 60 s while the tab is visible (§5.1).
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(true)
    }, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  // Debounced search: 300 ms, at least 2 characters (§4.3).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = searchText.trim()
      if (value === q || (value.length > 0 && value.length < 2)) return
      update({ q: value })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchText, q, update])

  const loadDetail = useCallback((id: string) => {
    setDetailError(null)
    return getBoardBooking(id)
      .then(setDetail)
      .catch((reason: unknown) => {
        setDetail(null)
        setDetailError(isApiError(reason) ? reason : null)
      })
  }, [])

  useEffect(() => {
    if (!bookingId) {
      setDetail(null)
      return
    }
    setDetail(null)
    void loadDetail(bookingId)
  }, [bookingId, loadDetail])

  useEffect(() => {
    if (detailError && isApiError(detailError, 'BOOKING_NOT_FOUND')) {
      toast.show('Không tìm thấy lịch hẹn.', 'warning')
      navigate(`/technician/board${search ? `?${search}` : ''}`, { replace: true })
      void load(true)
    }
  }, [detailError, navigate, search, toast, load])

  const openDetail = (id: string) => navigate(`/technician/board/${encodeURIComponent(id)}${search ? `?${search}` : ''}`)
  const closeDetail = () => navigate(`/technician/board${search ? `?${search}` : ''}`)

  const applyResult = useCallback((next: TransitionResult, previousStatus: BoardStatus) => {
    setData(current => {
      if (!current) return current
      const summary = { ...current.summary }
      if (previousStatus !== next.status) {
        summary[previousStatus] = Math.max(0, (summary[previousStatus] ?? 0) - 1)
        summary[next.status] = (summary[next.status] ?? 0) + 1
      }
      return { ...current, summary, items: current.items.map(item => (item.bookingId === next.bookingId ? { ...item, ...next } : item)) }
    })
    setDetail(current => (current && current.bookingId === next.bookingId ? { ...current, ...next } : current))
  }, [])

  const act = useCallback(
    async (item: BoardItem, action: BoardAction, extra: { reasonCode?: string; note?: string; actualCost?: number | null } = {}) => {
      if (pending) return false
      setPending({ bookingId: item.bookingId, action })
      setDialogError(null)
      try {
        const result = await transitionBooking(item.bookingId, {
          action,
          expectedStatus: item.status,
          ...(extra.reasonCode ? { reasonCode: extra.reasonCode } : {}),
          ...(extra.note ? { note: extra.note } : {}),
          ...(extra.actualCost !== undefined && extra.actualCost !== null ? { actualCost: extra.actualCost } : {}),
          source: 'BOARD',
        })
        applyResult(result, item.status)
        // The transition returns only the changed fields: refresh history and stage.
        if (detail?.bookingId === item.bookingId) void loadDetail(item.bookingId)
        if (action === 'CHECK_IN' || action === 'START') setProgressKey(key => key + 1)
        track('booking_transition', { action, reasonCode: extra.reasonCode ?? null, source: 'BOARD' })
        toast.show(SUCCESS[action] ?? 'Đã cập nhật.', 'success')
        return true
      } catch (reason) {
        const code = isApiError(reason) ? reason.code : 'UNKNOWN'
        track('booking_transition_failed', { action, errorCode: code })
        if (code === 'INVALID_STATUS_TRANSITION') {
          const current = isApiError(reason) ? String(reason.details?.currentStatus ?? '') : ''
          toast.show(`Lịch hẹn vừa được cập nhật (${bookingStatusLabel(current)}).`, 'warning')
          void loadDetail(item.bookingId)
          void load(true)
          return true
        }
        if (code === 'CONFIRM_DEADLINE_PASSED') {
          toast.show('Yêu cầu đã quá hạn xác nhận và bị huỷ tự động.', 'warning')
          void loadDetail(item.bookingId)
          void load(true)
          return true
        }
        if (code === 'CHECK_IN_NOT_TODAY') {
          toast.show('Lịch hẹn không phải hôm nay nên chưa check-in được.', 'warning')
          return false
        }
        if (code === 'NO_SHOW_TOO_EARLY') {
          setDialogError('Chưa tới lúc đánh dấu khách không đến.')
          return false
        }
        if (code === 'REASON_REQUIRED' || code === 'INVALID_REQUEST') {
          setDialogError(isApiError(reason) ? reason.message : 'Thông tin chưa hợp lệ.')
          return false
        }
        if (code === 'WORKSHOP_INACTIVE') {
          setInactive(true)
          return true
        }
        if (code === 'BOOKING_NOT_FOUND') {
          toast.show('Không tìm thấy lịch hẹn.', 'warning')
          closeDetail()
          void load(true)
          return true
        }
        toast.show('Tạm thời chưa thực hiện được, thử lại nhé.', 'error')
        return false
      } finally {
        setPending(null)
      }
    },
    // closeDetail depends on `search` only.
    [pending, applyResult, toast, loadDetail, load, search, detail?.bookingId],
  )

  const groups = useMemo(() => {
    const byDay = new Map<string, Map<string, BoardItem[]>>()
    for (const item of data?.items ?? []) {
      const day = byDay.get(item.bookingDate) ?? new Map<string, BoardItem[]>()
      const slot = day.get(item.timeSlot) ?? []
      slot.push(item)
      day.set(item.timeSlot, slot)
      byDay.set(item.bookingDate, day)
    }
    return [...byDay.entries()]
  }, [data])

  const pendingCount = data?.summary.PENDING ?? 0
  const filtered = statuses.length > 0 || q.length >= 2

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Lịch hẹn</h1>
          <p className="text-muted mt-1 flex items-center gap-2">
            {range === 'today' ? 'Hôm nay' : range === 'week' ? '7 ngày tới' : formatLongDay(from)}
            {refreshing && <span className="inline-flex items-center gap-1 text-xs"><span className="w-1.5 h-1.5 rounded-full bg-emerald animate-pulse" /> Đang cập nhật</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data && (
            <Link to="/technician/settings/booking">
              <Badge tone={data.confirmationMode === 'AUTO' ? 'success' : 'warning'} icon={<Settings2 className="w-3.5 h-3.5" />}>
                {data.confirmationMode === 'AUTO' ? 'Tự động xác nhận' : 'Xác nhận thủ công'}
              </Badge>
            </Link>
          )}
          <Button size="sm" icon={<QrCode className="w-4 h-4" />} onClick={() => navigate('/technician/check-in')}>
            Check-in QR
          </Button>
        </div>
      </div>

      {inactive && (
        <Notice tone="warning" className="mb-4" title="Xưởng đang tạm ngưng — chỉ xem, không thao tác được." />
      )}

      <Card className="mb-4 flex flex-col lg:flex-row lg:items-center gap-3">
        <div className="inline-flex p-1 rounded-xl bg-background/60 border border-border" role="tablist" aria-label="Khoảng ngày">
          {(
            [
              { key: 'today', label: 'Hôm nay' },
              { key: 'week', label: '7 ngày tới' },
              { key: 'day', label: 'Chọn ngày' },
            ] as const
          ).map(option => (
            <button
              key={option.key}
              role="tab"
              aria-selected={range === option.key}
              onClick={() => {
                const today = todayVn()
                if (option.key === 'today') update({ from: today, to: today })
                else if (option.key === 'week') update({ from: today, to: addDays(today, 6) })
                else update({ from: addDays(today, -1), to: addDays(today, -1) })
              }}
              className={cn(
                'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                range === option.key ? 'bg-emerald/10 text-emerald' : 'text-muted hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {range === 'day' && (
          <label className="inline-flex items-center gap-2 text-sm text-muted">
            <CalendarDays className="w-4 h-4" />
            <input
              type="date"
              value={from}
              min={addDays(todayVn(), -30)}
              onChange={event => event.target.value && update({ from: event.target.value, to: event.target.value })}
              className="bg-card border border-border rounded-lg px-2 py-1 text-foreground"
              aria-label="Ngày"
            />
          </label>
        )}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" aria-hidden />
          <input
            type="search"
            value={searchText}
            onChange={event => setSearchText(event.target.value)}
            placeholder="Mã lịch hẹn hoặc biển số"
            aria-label="Tìm lịch hẹn"
            className="w-full bg-card border border-border rounded-xl pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-emerald/60 focus:ring-4 focus:ring-emerald/15"
          />
        </div>
      </Card>

      {/* One control for count and filter: the old count cards and status chips repeated each other. */}
      <div className="flex flex-wrap gap-2 mb-4" aria-label="Lọc trạng thái">
        {STATUSES.map(status => {
          const on = statuses.includes(status)
          return (
            <button
              key={status}
              type="button"
              aria-pressed={on}
              onClick={() => update({ statuses: on ? statuses.filter(item => item !== status) : [...statuses, status] })}
              className={cn(
                'min-h-11 inline-flex items-center gap-2 rounded-xl border px-3.5 text-sm font-medium transition-colors',
                on ? 'bg-emerald/10 text-emerald border-emerald/30' : 'bg-card text-muted border-border hover:text-foreground',
              )}
            >
              {BOOKING_STATUS[status].label}
              <span className={cn('font-mono font-semibold tabular-nums', on ? 'text-emerald' : 'text-foreground')}>
                {data ? data.summary[status] ?? 0 : '–'}
              </span>
            </button>
          )
        })}
      </div>

      {pendingCount > 0 && (
        <Notice
          tone="warning"
          className="mb-4"
          title={`Có ${pendingCount} yêu cầu chờ bạn xác nhận`}
          action={
            <Button size="sm" variant="secondary" onClick={() => update({ statuses: ['PENDING'] })}>
              Xem
            </Button>
          }
        />
      )}
      {staleError && <Notice tone="warning" className="mb-4" title="Không cập nhật được — dữ liệu có thể chưa mới nhất." />}

      {error ? (
        <Card>
          <ErrorState title="Không thể tải lịch hẹn." traceId={error.traceId} onRetry={() => void load()} />
        </Card>
      ) : !data ? (
        <Card className="space-y-3" aria-busy>
          {[0, 1, 2, 3, 4].map(index => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </Card>
      ) : data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<CalendarDays className="w-5 h-5" />}
            title={filtered ? 'Không có lịch hẹn phù hợp bộ lọc.' : emptyText(range)}
            action={
              filtered ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSearchText('')
                    update({ statuses: [], q: '' })
                  }}
                >
                  Xoá bộ lọc
                </Button>
              ) : undefined
            }
          />
        </Card>
      ) : (
        <div className="space-y-5">
          {groups.map(([day, slots]) => (
            <section key={day}>
              {range !== 'today' && <h2 className="text-sm font-semibold text-foreground mb-2">{formatLongDay(day)}</h2>}
              {/* Mobile: one card per booking, grouped by slot (§15). */}
              <ul className="md:hidden space-y-2">
                {[...slots.entries()].flatMap(([slot, items]) =>
                  items.map(item => {
                    const status = BOOKING_STATUS[item.status]
                    const quick = QUICK.filter(button => item.allowedActions.includes(button.action))
                    return (
                      <li key={item.bookingId}>
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => openDetail(item.bookingId)}
                          onKeyDown={event => event.key === 'Enter' && openDetail(item.bookingId)}
                          className={cn(
                            'rounded-2xl border bg-card p-4 elevation-sm cursor-pointer',
                            bookingId === item.bookingId ? 'border-emerald/40' : 'border-border',
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-semibold text-foreground">
                                <span className="font-mono">{slotLabel(slot)}</span> · {item.customer.fullName}
                              </p>
                              <p className="text-xs text-muted mt-0.5 truncate">
                                {item.vehicle.modelName} · <span className="font-mono">{formatLicensePlate(item.vehicle.licensePlate)}</span>
                              </p>
                              <p className="text-xs text-muted font-mono mt-0.5">{item.bookingCode ?? '—'}</p>
                            </div>
                            {status && <Badge tone={status.tone}>{status.label}</Badge>}
                          </div>
                          {(item.attendanceConfirmedAt || item.confirmDeadline) && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {item.attendanceConfirmedAt && <span className="text-xs text-emerald">✓ Khách đã xác nhận đến</span>}
                              {item.confirmDeadline && <DeadlineBadge deadline={item.confirmDeadline} />}
                            </div>
                          )}
                          {!inactive && quick.length > 0 && (
                            <div className="mt-3 flex gap-2" onClick={event => event.stopPropagation()}>
                              {quick.map(({ action, label, icon: Icon }) => (
                                <Button
                                  key={action}
                                  size="sm"
                                  className="flex-1 min-h-11"
                                  variant={action === 'ACCEPT' ? 'primary' : 'secondary'}
                                  icon={<Icon className="w-4 h-4" />}
                                  loading={pending?.bookingId === item.bookingId && pending.action === action}
                                  disabled={pending?.bookingId === item.bookingId}
                                  onClick={() => void act(item, action)}
                                >
                                  {label}
                                </Button>
                              ))}
                            </div>
                          )}
                        </div>
                      </li>
                    )
                  }),
                )}
              </ul>
              <Card className="p-0 overflow-hidden hidden md:block">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted">
                        <th className="px-4 py-2.5 font-medium">Giờ</th>
                        <th className="px-4 py-2.5 font-medium">Mã</th>
                        <th className="px-4 py-2.5 font-medium">Khách</th>
                        <th className="px-4 py-2.5 font-medium">Xe</th>
                        <th className="px-4 py-2.5 font-medium">Trạng thái</th>
                        <th className="px-4 py-2.5 font-medium hidden xl:table-cell">Nhãn</th>
                        <th className="px-4 py-2.5 font-medium text-right">Hành động</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...slots.entries()].flatMap(([slot, items]) =>
                        items.map((item, index) => {
                          const status = BOOKING_STATUS[item.status]
                          const quick = QUICK.filter(button => item.allowedActions.includes(button.action))
                          return (
                            <tr
                              key={item.bookingId}
                              tabIndex={0}
                              onClick={() => openDetail(item.bookingId)}
                              onKeyDown={event => event.key === 'Enter' && openDetail(item.bookingId)}
                              className={cn(
                                'border-b border-border last:border-0 cursor-pointer hover:bg-card-hover focus:bg-card-hover focus:outline-none',
                                bookingId === item.bookingId && 'bg-emerald/5',
                              )}
                            >
                              <td className="px-4 py-3 font-mono text-foreground whitespace-nowrap">{index === 0 ? slotLabel(slot) : ''}</td>
                              <td className="px-4 py-3 font-mono text-muted whitespace-nowrap">{item.bookingCode ?? '—'}</td>
                              <td className="px-4 py-3 text-foreground whitespace-nowrap">{item.customer.fullName}</td>
                              <td className="px-4 py-3 text-muted whitespace-nowrap">
                                {item.vehicle.modelName} · <span className="font-mono">{formatLicensePlate(item.vehicle.licensePlate)}</span>
                              </td>
                              <td className="px-4 py-3">{status && <Badge tone={status.tone}>{status.label}</Badge>}</td>
                              <td className="px-4 py-3 hidden xl:table-cell">
                                {item.attendanceConfirmedAt && <span className="text-xs text-emerald">✓ Khách đã xác nhận đến</span>}
                                {item.confirmDeadline && <DeadlineBadge deadline={item.confirmDeadline} />}
                              </td>
                              <td className="px-4 py-3 text-right whitespace-nowrap" onClick={event => event.stopPropagation()}>
                                {!inactive &&
                                  quick.map(({ action, label, icon: Icon }) => (
                                    <Button
                                      key={action}
                                      size="sm"
                                      variant={action === 'ACCEPT' ? 'primary' : 'secondary'}
                                      icon={<Icon className="w-3.5 h-3.5" />}
                                      loading={pending?.bookingId === item.bookingId && pending.action === action}
                                      disabled={pending?.bookingId === item.bookingId}
                                      onClick={() => void act(item, action)}
                                      className="ml-1.5"
                                    >
                                      {label}
                                    </Button>
                                  ))}
                              </td>
                            </tr>
                          )
                        }),
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            </section>
          ))}
        </div>
      )}

      <Drawer open={Boolean(bookingId)} onClose={closeDetail} title="Chi tiết lịch hẹn" width="sm:w-[30rem]">
        {detail ? (
          <BoardBookingDetail
            detail={detail}
            pendingAction={pending?.bookingId === detail.bookingId ? pending.action : null}
            readOnly={inactive}
            dialogError={dialogError}
            progressKey={progressKey}
            onAction={(action, extra) => act(detail, action, extra)}
          />
        ) : detailError && !isApiError(detailError, 'BOOKING_NOT_FOUND') ? (
          <ErrorState compact traceId={detailError.traceId} onRetry={() => bookingId && void loadDetail(bookingId)} />
        ) : (
          <div className="p-5 space-y-3" aria-busy>
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}
      </Drawer>
    </div>
  )
}
