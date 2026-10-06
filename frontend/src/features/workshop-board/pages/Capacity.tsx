import { useCallback, useEffect, useState } from 'react'
import { Lock } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { SelectInput, TextArea } from '@/shared/ui/Field'
import NumberStepper from '@/shared/ui/NumberStepper'
import Skeleton from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { cn } from '@/shared/ui/cn'
import { track } from '@/shared/utils/track'
import { dayChip, slotLabel, todayVn } from '@/features/bookings/utils'
import { getCapacity, saveSlotBlock } from '../api'
import { capacitySlotState } from '../utils'
import type { CapacityData, CapacitySlot } from '../types'

const BLOCK_REASONS = [
  { value: 'PHONE_BOOKING', label: 'Khách gọi điện' },
  { value: 'WALK_IN', label: 'Khách vãng lai' },
  { value: 'MAINTENANCE', label: 'Bảo trì' },
  { value: 'OTHER', label: 'Khác' },
]

interface Editing {
  date: string
  slot: CapacitySlot
  blockedCount: string
  reason: string
  note: string
  maxBlock: number
}

/** SCR-804 — capacity of the next 7 days and slot blocks (API-WB-05 / WB-06). */
export default function Capacity() {
  const toast = useToast()
  const [data, setData] = useState<CapacityData | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    getCapacity(todayVn())
      .then(setData)
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }, [])

  useEffect(load, [load])

  function open(date: string, slot: CapacitySlot) {
    setFormError(null)
    setEditing({
      date,
      slot,
      blockedCount: String(slot.blocked),
      reason: slot.blockReason ?? 'PHONE_BOOKING',
      note: slot.blockNote ?? '',
      maxBlock: slot.maxBlock,
    })
  }

  function patchSlot(date: string, next: Partial<CapacitySlot> & { timeSlot: string }) {
    setData(current =>
      current
        ? {
            ...current,
            days: current.days.map(day =>
              day.date === date ? { ...day, slots: day.slots.map(slot => (slot.timeSlot === next.timeSlot ? { ...slot, ...next } : slot)) } : day,
            ),
          }
        : current,
    )
  }

  async function save(count: number) {
    if (!editing) return
    if (count > 0 && editing.reason === 'OTHER' && !editing.note.trim()) {
      setFormError('Vui lòng ghi chú lý do khoá.')
      return
    }
    if (count > editing.maxBlock) {
      setFormError(`Chỉ còn ${editing.maxBlock} chỗ trống để khoá.`)
      return
    }
    setSaving(true)
    setFormError(null)
    try {
      const result = await saveSlotBlock({
        date: editing.date,
        timeSlot: editing.slot.timeSlot,
        blockedCount: count,
        ...(count > 0 ? { reason: editing.reason } : {}),
        ...(count > 0 && editing.note.trim() ? { note: editing.note.trim() } : {}),
      })
      patchSlot(editing.date, {
        timeSlot: editing.slot.timeSlot,
        blocked: result.blocked,
        occupied: result.occupied,
        remaining: result.remaining,
        maxBlock: result.maxBlock,
        blockReason: count > 0 ? editing.reason : null,
        blockNote: count > 0 ? editing.note.trim() || null : null,
      })
      track('slot_block_saved', { blockedCount: count, reason: count > 0 ? editing.reason : null })
      toast.show(count > 0 ? `Đã khoá ${count} chỗ.` : 'Đã gỡ khoá.', 'success')
      setEditing(null)
    } catch (reason) {
      if (isApiError(reason) && reason.code === 'BLOCK_EXCEEDS_FREE_CAPACITY') {
        const max = Number(reason.details?.maxBlock ?? 0)
        setEditing(current => (current ? { ...current, maxBlock: max, blockedCount: String(Math.min(Number(current.blockedCount) || 0, max)) } : current))
        setFormError(`Chỉ còn ${max} chỗ trống để khoá.`)
      } else if (isApiError(reason, 'BLOCK_DATE_OUT_OF_RANGE') || isApiError(reason, 'SLOT_OUT_OF_HOURS')) {
        setFormError(isApiError(reason) ? reason.message : 'Khung không hợp lệ.')
      } else {
        toast.show('Tạm thời chưa lưu được, thử lại nhé.', 'error')
      }
    } finally {
      setSaving(false)
    }
  }

  const allClosed = data?.days.every(day => day.isClosed)
  const times = data ? [...new Set(data.days.flatMap(day => day.slots.map(slot => slot.timeSlot)))].sort() : []

  return (
    <div className="p-4 sm:p-6 xl:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Sức chứa & khoá chỗ</h1>
        <p className="text-muted mt-1">
          {data
            ? `${data.totalTechnicians} kỹ thuật viên · giữ ${data.emergencySlotsReserved} chỗ khẩn cấp mỗi khung. Khoá chỗ cho khách gọi điện hoặc vãng lai.`
            : 'Khoá chỗ cho khách gọi điện hoặc vãng lai, có hiệu lực ngay.'}
        </p>
      </div>

      {error ? (
        <Card>
          <ErrorState traceId={error.traceId} onRetry={load} />
        </Card>
      ) : !data ? (
        <Card aria-busy>
          <Skeleton className="h-64 w-full" />
        </Card>
      ) : allClosed ? (
        <Card>
          <EmptyState title="Xưởng không mở cửa trong 7 ngày tới. Kiểm tra giờ hoạt động." />
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse min-w-[720px]">
              <thead>
                <tr>
                  <th className="px-3 py-3 text-left text-xs font-medium text-muted w-16">Khung</th>
                  {data.days.map(day => {
                    const chip = dayChip(day.date)
                    return (
                      <th key={day.date} className={cn('px-2 py-3 text-center text-xs font-medium', day.isClosed ? 'text-muted/60' : 'text-foreground')}>
                        <span className="block">{chip.weekday}</span>
                        <span className="block font-semibold">{chip.dayMonth}</span>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {times.map(time => (
                  <tr key={time} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-muted">{slotLabel(time)}</td>
                    {data.days.map(day => {
                      if (day.isClosed) {
                        return (
                          <td key={day.date} className="px-2 py-2 text-center text-xs text-muted bg-foreground/[0.03]">
                            Nghỉ
                          </td>
                        )
                      }
                      const slot = day.slots.find(item => item.timeSlot === time)
                      if (!slot) return <td key={day.date} />
                      const state = capacitySlotState(slot)
                      const full = state !== 'open'
                      return (
                        <td key={day.date} className="px-1.5 py-1.5">
                          <button
                            type="button"
                            onClick={() => open(day.date, slot)}
                            className={cn(
                              'w-full min-h-14 rounded-xl border px-2.5 py-2 text-left text-xs leading-tight transition-colors',
                              full ? 'border-border bg-foreground/[0.04]' : slot.blocked > 0 ? 'border-warning/30 bg-warning/5' : 'border-border bg-card hover:bg-card-hover',
                            )}
                            aria-label={`${slotLabel(time)} ${day.date}: đã đặt ${slot.occupied}, khoá ${slot.blocked}, còn nhận ${slot.remaining}`}
                          >
                            {/* Seats left lead; booked and locked lines appear only when non-zero, so busy slots stand out. */}
                            {state === 'closed' ? (
                              <span className="block text-sm text-muted">Không nhận</span>
                            ) : full ? (
                              <span className="block text-sm font-semibold text-foreground">Hết chỗ</span>
                            ) : (
                              <span className="block text-muted">
                                <span className="font-mono text-base font-semibold tabular-nums text-foreground">{slot.remaining}</span> còn
                              </span>
                            )}
                            {slot.occupied > 0 && <span className="block mt-0.5 text-muted">Đã đặt {slot.occupied}</span>}
                            {slot.blocked > 0 && (
                              <span className="block mt-0.5 text-warning">
                                <Lock className="inline w-3 h-3 mr-0.5" aria-hidden />
                                Khoá {slot.blocked}
                              </span>
                            )}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Dialog
        open={editing !== null}
        onClose={() => !saving && setEditing(null)}
        title={editing ? `Khoá chỗ · ${slotLabel(editing.slot.timeSlot)} ${dayChip(editing.date).dayMonth}` : ''}
        description={editing ? `Đã đặt ${editing.slot.occupied} · còn trống tối đa ${editing.maxBlock} chỗ để khoá.` : undefined}
        dismissable={!saving}
        className="sm:max-w-md"
        footer={
          editing && (
            <>
              {editing.slot.blocked > 0 && (
                <Button variant="ghost" onClick={() => void save(0)} disabled={saving} className="sm:mr-auto">
                  Gỡ khoá
                </Button>
              )}
              <Button variant="secondary" onClick={() => setEditing(null)} disabled={saving}>
                Huỷ
              </Button>
              <Button loading={saving} loadingText="Đang lưu…" onClick={() => void save(Number(editing.blockedCount) || 0)}>
                Lưu
              </Button>
            </>
          )
        }
      >
        {editing && (
          <div className="space-y-4">
            <NumberStepper
              label="Số chỗ khoá"
              value={editing.blockedCount}
              min={0}
              max={editing.maxBlock}
              disabled={saving}
              onChange={value => setEditing(current => (current ? { ...current, blockedCount: value } : current))}
              error={formError && formError.startsWith('Chỉ còn') ? formError : undefined}
            />
            {Number(editing.blockedCount) > 0 && (
              <>
                <SelectInput
                  label="Lý do"
                  value={editing.reason}
                  disabled={saving}
                  onChange={event => setEditing(current => (current ? { ...current, reason: event.target.value } : current))}
                >
                  {BLOCK_REASONS.map(reason => (
                    <option key={reason.value} value={reason.value}>
                      {reason.label}
                    </option>
                  ))}
                </SelectInput>
                <TextArea
                  label="Ghi chú"
                  required={editing.reason === 'OTHER'}
                  optional={editing.reason !== 'OTHER'}
                  rows={2}
                  maxLength={255}
                  value={editing.note}
                  disabled={saving}
                  onChange={event => setEditing(current => (current ? { ...current, note: event.target.value } : current))}
                  error={formError && !formError.startsWith('Chỉ còn') ? formError : undefined}
                />
              </>
            )}
          </div>
        )}
      </Dialog>
    </div>
  )
}
