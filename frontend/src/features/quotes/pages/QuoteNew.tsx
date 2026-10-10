import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { FileText, Store } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import Spinner from '@/shared/ui/Spinner'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { createQuote } from '../api'

/** `/quotes/new?userVehicleId&workshopId&odoMilestone` — creates the draft then replaces the route (FE §5 #1). */
export default function QuoteNew() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const userVehicleId = searchParams.get('userVehicleId')
  const workshopId = searchParams.get('workshopId')
  const odo = searchParams.get('odoMilestone')
  const odoMilestone = odo && /^\d+$/.test(odo) ? Number(odo) : null
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  // StrictMode runs effects twice in development: create the draft once per attempt.
  const started = useRef(-1)

  useEffect(() => {
    if (!userVehicleId || !workshopId || odoMilestone === null || started.current === attempt) return
    started.current = attempt
    setError(null)
    createQuote({ userVehicleId, workshopId, odoMilestone })
      .then(quote => {
        track('quote_draft_created', {
          source: 'UI',
          hasReferencePrice: quote.items.some(item => !item.covered && item.priceSource === 'REFERENCE_PRICE'),
        })
        navigate(`/quotes/${encodeURIComponent(quote.quoteId)}`, { replace: true })
      })
      .catch((reason: unknown) => {
        if (isApiError(reason, 'NO_MAINTENANCE_RULE')) {
          toast.show('Chưa có định mức bảo dưỡng cho mốc này nên chưa lập được báo giá.', 'warning')
          navigate(`/estimate?odoMilestone=${odoMilestone}`, { replace: true })
          return
        }
        if (isApiError(reason, 'VEHICLE_NOT_FOUND')) {
          navigate('/dashboard', { replace: true })
          return
        }
        setError(isApiError(reason) ? reason : null)
      })
  }, [userVehicleId, workshopId, odoMilestone, attempt, navigate, toast])

  if (!userVehicleId || !workshopId || odoMilestone === null) return <Navigate to="/estimate" replace />

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-xl">
      <Card>
        {isApiError(error, 'WORKSHOP_INACTIVE') ? (
          <EmptyState
            icon={<Store className="w-5 h-5" />}
            title="Xưởng hiện không nhận khách"
            description="Bạn chọn xưởng khác để lập báo giá nhé."
            action={<Button onClick={() => navigate(`/estimate?odoMilestone=${odoMilestone}`)}>Chọn xưởng khác</Button>}
          />
        ) : error ? (
          <ErrorState title="Chưa lập được báo giá." traceId={error.traceId} onRetry={() => setAttempt(count => count + 1)} />
        ) : (
          <EmptyState icon={<FileText className="w-5 h-5" />} title="Đang lập báo giá" description={<Spinner className="w-5 h-5 mx-auto mt-2" />} />
        )}
      </Card>
    </div>
  )
}
