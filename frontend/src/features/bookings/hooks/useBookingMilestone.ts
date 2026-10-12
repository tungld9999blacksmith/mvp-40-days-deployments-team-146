import { useMaintenanceStatus } from '@/features/vehicles/hooks/useVehicleQueries'
import { useBookingWizard } from '../context/BookingWizardContext'

/** Milestone being booked: the one in the query, else the next milestone of the vehicle. */
export function useBookingMilestone(): number | null {
  const { vehicle, params } = useBookingWizard()
  const status = useMaintenanceStatus(vehicle.userVehicleId)
  return params.odoMilestone ?? status.data?.nextMilestone?.odoMilestoneKm ?? null
}
