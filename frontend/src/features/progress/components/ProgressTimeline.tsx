import { useCallback, useEffect, useState } from 'react'
import { Activity, CarFront, PackageSearch, Phone } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import { Card, CardHeader } from '@/shared/ui/Card'
import Skeleton from '@/shared/ui/Skeleton'
import { Notice } from '@/shared/ui/States'
import { getBookingProgress } from '../api'
import type { Progress } from '../types'
import StageStepper from './StageStepper'

const REFRESH_MS = 60_000

/**
 * SCR-1302 — owner timeline inside the ticket. Refreshes every 60 s while the tab is visible and
 * the progress is not frozen (AC-FE-1303); a 404 hides the block (feature off / not visible).
 */
export default function ProgressTimeline({
  bookingId,
  workshop,
}: {
  bookingId: string
  workshop: { name: string; address: string | null; phone: string | null }
}) {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [hidden, setHidden] = useState(false)

  const load = useCallback(
    () =>
      getBookingProgress(bookingId)
        .then(setProgress)
        .catch((reason: unknown) => {
          if (isApiError(reason) && (reason.status === 404 || reason.code === 'FEATURE_DISABLED')) setHidden(true)
        }),
    [bookingId],
  )

  useEffect(() => {
    void load()
  }, [load])

  const frozen = progress?.isFrozen ?? false
  useEffect(() => {
    if (frozen || hidden) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, REFRESH_MS)
    const onVisible = () => document.visibilityState === 'visible' && void load()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [frozen, hidden, load])

  if (hidden) return null
  if (!progress) {
    return (
      <Card>
        <Skeleton className="h-3 w-24 mb-4" />
        <Skeleton className="h-10 w-full" />
      </Card>
    )
  }

  const waitingNote =
    progress.currentStage === 'WAITING_PARTS' ? [...progress.entries].reverse().find(entry => entry.stage === 'WAITING_PARTS')?.note : null

  return (
    <div className="space-y-3">
      {progress.currentStage === 'READY_FOR_PICKUP' && progress.bookingStatus !== 'COMPLETED' && (
        <Notice tone="success" icon={<CarFront className="w-4 h-4" />} title="Xe đã sẵn sàng, bạn có thể đến nhận">
          {workshop.name}
          {workshop.address ? ` · ${workshop.address}` : ''}
          {workshop.phone && (
            <a href={`tel:${workshop.phone}`} className="ml-2 inline-flex items-center gap-1 text-emerald font-medium">
              <Phone className="w-3.5 h-3.5" /> {workshop.phone}
            </a>
          )}
        </Notice>
      )}
      {waitingNote && (
        <Notice tone="warning" icon={<PackageSearch className="w-4 h-4" />} title="Xưởng đang chờ phụ tùng">
          {waitingNote}
        </Notice>
      )}
      <Card>
        <CardHeader title="Tiến độ dịch vụ" icon={<Activity className="w-4 h-4 text-muted" />} />
        <StageStepper progress={progress} showActor={false} />
      </Card>
    </div>
  )
}
