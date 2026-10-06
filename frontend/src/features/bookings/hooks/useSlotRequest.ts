import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isApiError } from '@/shared/api/client'
import { useToast } from '@/shared/ui/Toast'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { getAvailability } from '../api'
import { useBookingWizard } from '../context/BookingWizardContext'
import type { Alternative } from '../types'
import { bookingErrorMessage, slotLabel, tokenExpiry } from '../utils'

export interface SlotTarget {
  workshopId: string
  date: string
  timeSlot: string
  /** Name of a workshop that is not in the nearby list yet (alternatives). */
  name?: string
}

/**
 * API-BK-02 with `timeSlot`: gets a confirmation token and opens the summary card,
 * or exposes up to 3 alternatives when the slot is full (FE §3.4, §4.5).
 */
export function useSlotRequest() {
  const navigate = useNavigate()
  const toast = useToast()
  const { params, searchFor, setCard, workshopById, rememberWorkshops } = useBookingWizard()
  const [pending, setPending] = useState<string | null>(null)
  const [alternatives, setAlternatives] = useState<Alternative[] | null>(null)

  const showAlternatives = useCallback((list: Alternative[]) => {
    track('booking_slot_full_shown', { alternativesCount: list.length })
    setAlternatives(list)
  }, [])

  const closeAlternatives = useCallback(() => setAlternatives(null), [])

  const requestSlot = useCallback(
    async (target: SlotTarget, extraQuery: { quoteId?: string | null } = {}) => {
      const label = slotLabel(target.timeSlot)
      if (target.name && !workshopById(target.workshopId)) {
        rememberWorkshops([
          {
            workshopId: target.workshopId,
            name: target.name,
            address: '',
            region: '',
            distanceKm: null,
            isPreferred: false,
            operatingHoursToday: null,
            availability: null,
          },
        ])
      }
      setPending(label)
      try {
        // Alternatives are costly to compute: only ask for them when the slot is not free.
        const data = await getAvailability({ workshopId: target.workshopId, date: target.date, timeSlot: label, withAlternatives: false })
        const requested = data.requested
        if (requested?.available && requested.confirmationToken) {
          setAlternatives(null)
          setCard({
            workshopId: target.workshopId,
            date: target.date,
            timeSlot: requested.timeSlot,
            confirmationToken: requested.confirmationToken,
            expiresAt: tokenExpiry(Date.now()),
            idempotencyKey: newId(),
          })
          const sameProposalSlot = params.workshopId === target.workshopId && params.date === target.date && slotLabel(params.timeSlot ?? '') === label
          navigate(`/booking/confirm${searchFor({ proposalId: sameProposalSlot ? params.proposalId : null, workshopId: target.workshopId, date: target.date, timeSlot: label, ...extraQuery })}`)
          return true
        }
        const withAlternatives = await getAvailability({ workshopId: target.workshopId, date: target.date, timeSlot: label })
        showAlternatives(withAlternatives.alternatives)
        return false
      } catch (reason) {
        const message = isApiError(reason) ? bookingErrorMessage(reason.code) : null
        toast.show(message ?? 'Không kiểm tra được khung giờ, bạn thử lại nhé.', 'error')
        return false
      } finally {
        setPending(null)
      }
    },
    [params, navigate, searchFor, setCard, toast, workshopById, rememberWorkshops, showAlternatives],
  )

  return { pending, alternatives, showAlternatives, closeAlternatives, requestSlot }
}
