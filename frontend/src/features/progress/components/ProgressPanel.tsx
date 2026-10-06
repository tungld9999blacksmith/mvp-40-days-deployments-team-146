import { useCallback, useEffect, useState } from 'react'
import { Activity, RotateCcw } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card, CardHeader } from '@/shared/ui/Card'
import Dialog from '@/shared/ui/Dialog'
import { TextArea } from '@/shared/ui/Field'
import Skeleton from '@/shared/ui/Skeleton'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { addProgressStage, getWorkshopProgress } from '../api'
import type { Progress, Stage } from '../types'
import StageStepper, { STAGE_LABEL } from './StageStepper'

const PII_HINT = 'Khách hàng sẽ thấy ghi chú này. Không nhập số điện thoại, VIN hay thông tin cá nhân.'

/**
 * SCR-1301 — progress panel in the Board detail. Buttons come only from `nextStages`
 * (AC-FE-1301); every write sends `expectedCurrentStage` (EF-1302).
 */
export default function ProgressPanel({
  bookingId,
  bookingStatus,
  refreshKey,
  onStageChange,
}: {
  bookingId: string
  bookingStatus: string
  /** Changes after CHECK_IN / START so the panel reloads (us-057 §3). */
  refreshKey: number
  onStageChange?: (stage: Stage | null) => void
}) {
  const toast = useToast()
  const [progress, setProgress] = useState<Progress | null>(null)
  const [hidden, setHidden] = useState(false)
  const [target, setTarget] = useState<Stage | null>(null)
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(
    () =>
      getWorkshopProgress(bookingId)
        .then(data => {
          setProgress(data)
          onStageChange?.(data.currentStage)
          track('progress_viewed_by_owner', { currentStage: data.currentStage })
        })
        .catch((reason: unknown) => {
          if (isApiError(reason) && (reason.status === 404 || reason.code === 'FEATURE_DISABLED')) setHidden(true)
        }),
    [bookingId, onStageChange],
  )

  useEffect(() => {
    void load()
  }, [load, refreshKey, bookingStatus])

  if (hidden) return null
  if (!['CHECKED_IN', 'IN_PROGRESS', 'COMPLETED'].includes(bookingStatus)) {
    return (
      <Card>
        <CardHeader title="Tiến độ" icon={<Activity className="w-4 h-4 text-muted" />} />
        <p className="text-sm text-muted">Tiến độ bắt đầu khi xe được check-in.</p>
      </Card>
    )
  }
  if (!progress) {
    return (
      <Card>
        <Skeleton className="h-3 w-24 mb-4" />
        <Skeleton className="h-10 w-full" />
      </Card>
    )
  }

  const current = progress
  const next = current.nextStages ?? []

  function open(stage: Stage) {
    setTarget(stage)
    setNote('')
    setNoteError(null)
  }

  async function save() {
    if (!target) return
    const text = note.trim()
    if (target === 'WAITING_PARTS' && (text.length < 10 || text.length > 500)) {
      setNoteError('Ghi chú chờ phụ tùng cần 10–500 ký tự.')
      return
    }
    if (text.length > 500) {
      setNoteError('Tối đa 500 ký tự.')
      return
    }
    setSaving(true)
    try {
      const result = await addProgressStage(bookingId, { stage: target, ...(text ? { note: text } : {}), expectedCurrentStage: current.currentStage })
      track('progress_stage_added', { stage: target, fromStage: current.currentStage })
      setProgress(result)
      onStageChange?.(result.currentStage)
      setTarget(null)
      toast.show(`Đã cập nhật: ${STAGE_LABEL[target]}.`, 'success')
    } catch (reason) {
      if (isApiError(reason, 'NOTE_REQUIRED')) {
        setNoteError('Ghi chú chờ phụ tùng cần 10–500 ký tự.')
      } else {
        setTarget(null)
        if (isApiError(reason, 'PROGRESS_CHANGED')) toast.show('Tiến độ vừa được cập nhật.', 'warning')
        else if (isApiError(reason, 'BOOKING_NOT_IN_PROGRESS')) toast.show('Lịch hẹn không còn ở trạng thái đang làm.', 'warning')
        else if (!isApiError(reason, 'INVALID_STAGE_TRANSITION')) toast.show('Tạm thời chưa cập nhật được, thử lại nhé.', 'error')
        void load()
      }
    } finally {
      setSaving(false)
    }
  }

  const rework = target === 'SERVICING' && current.currentStage === 'QUALITY_CHECK'

  return (
    <Card>
      <CardHeader title="Tiến độ 6 bước" icon={<Activity className="w-4 h-4 text-muted" />} />
      <StageStepper progress={current} showActor />
      {next.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
          {next.map(stage => (
            <Button
              key={stage}
              size="sm"
              variant={stage === 'READY_FOR_PICKUP' || stage === 'QUALITY_CHECK' ? 'primary' : 'secondary'}
              icon={stage === 'SERVICING' && current.currentStage === 'QUALITY_CHECK' ? <RotateCcw className="w-3.5 h-3.5" /> : undefined}
              onClick={() => open(stage)}
            >
              {stage === 'SERVICING' && current.currentStage === 'QUALITY_CHECK' ? 'Làm lại (về Đang bảo dưỡng)' : STAGE_LABEL[stage]}
            </Button>
          ))}
        </div>
      )}

      <Dialog
        open={target !== null}
        onClose={() => !saving && setTarget(null)}
        title={target ? (rework ? 'Làm lại — về Đang bảo dưỡng' : `Chuyển sang: ${STAGE_LABEL[target]}`) : ''}
        description={rework ? 'Nên ghi lý do làm lại để khách hiểu.' : undefined}
        dismissable={!saving}
        className="sm:max-w-md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)} disabled={saving}>
              Huỷ
            </Button>
            <Button loading={saving} loadingText="Đang lưu…" onClick={() => void save()}>
              Cập nhật
            </Button>
          </>
        }
      >
        <TextArea
          label="Ghi chú"
          required={target === 'WAITING_PARTS'}
          optional={target !== 'WAITING_PARTS'}
          rows={3}
          maxLength={500}
          value={note}
          disabled={saving}
          placeholder={target === 'WAITING_PARTS' ? 'Ví dụ: Chờ má phanh trước, dự kiến có lúc 14:00' : undefined}
          onChange={event => setNote(event.target.value)}
          aside={<span className="text-xs text-muted font-mono">{note.length}/500</span>}
          helper={PII_HINT}
          error={noteError ?? undefined}
        />
      </Dialog>
    </Card>
  )
}
