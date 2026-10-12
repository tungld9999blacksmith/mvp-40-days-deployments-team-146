import type { TripPlan } from './types'

export function tripBookingLink(vehicleId: string, plan: TripPlan): string {
  const query = new URLSearchParams({ userVehicleId: vehicleId })
  if (plan.advice.milestoneKm !== null) query.set('odoMilestone', String(plan.advice.milestoneKm))
  if (plan.advice.preferredWorkshop?.workshop_id) query.set('workshopId', plan.advice.preferredWorkshop.workshop_id)
  // A preferred date is only a suggestion; availability stays in the booking flow.
  if (plan.advice.preferredServiceWindow?.suggestedDate) query.set('date', plan.advice.preferredServiceWindow.suggestedDate)
  return `/booking?${query}`
}

export function validateTrip(departure: string, returnDate: string, distance: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(departure)) return 'Chọn ngày khởi hành.'
  if (returnDate && returnDate < departure) return 'Ngày về không được trước ngày đi.'
  const km = Number(distance)
  if (!Number.isInteger(km) || km < 1 || km > 20_000) return 'Nhập tổng quãng đường từ 1 đến 20.000 km.'
  return null
}
