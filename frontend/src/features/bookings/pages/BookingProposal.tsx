import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { apiGet } from "@/shared/api/client"
import { newId } from "@/shared/utils/id"
import { useBookingWizard } from "../context/BookingWizardContext"
import type { NearbyWorkshop } from "../types"

export default function BookingProposal() {
  const { params, vehicle, setCard, rememberWorkshops } = useBookingWizard()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    if (!params.proposalId) {
      setError("Thiếu mã đề xuất.")
      return
    }
    setError(null)
    apiGet<{
      proposal: {
        userVehicleId: string
        workshopId: string
        date: string
        timeSlot: string
        odoMilestone: number
      }
      confirmationToken: string
      workshop: NearbyWorkshop
    }>(`/booking-proposals/${encodeURIComponent(params.proposalId)}`, {
      signal: controller.signal,
    })
      .then(({ proposal: p, confirmationToken, workshop }) => {
        if (controller.signal.aborted) return
        if (p.userVehicleId !== vehicle.userVehicleId) {
          setError("Đề xuất không thuộc xe đang chọn.")
          return
        }
        rememberWorkshops([workshop])
        setCard({
          workshopId: p.workshopId,
          date: p.date,
          timeSlot: p.timeSlot,
          confirmationToken,
          expiresAt: Date.now() + 10 * 60_000,
          idempotencyKey: newId(),
        })
        const query = new URLSearchParams({
          proposalId: params.proposalId!,
          workshopId: p.workshopId,
          date: p.date,
          timeSlot: p.timeSlot,
          odoMilestone: String(p.odoMilestone),
        })
        navigate(`/booking/confirm?${query}`, { replace: true })
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Không kiểm tra được đề xuất.",
          )
      })
    return () => controller.abort()
  }, [
    params.proposalId,
    vehicle.userVehicleId,
    setCard,
    rememberWorkshops,
    navigate,
    attempt,
  ])
  return (
    <div className="space-y-3">
      <p role={error ? "alert" : "status"}>
        {error ?? "Đang kiểm tra lại lịch trống…"}
      </p>
      {error && (
        <button onClick={() => setAttempt((a) => a + 1)}>Thử lại</button>
      )}
    </div>
  )
}
