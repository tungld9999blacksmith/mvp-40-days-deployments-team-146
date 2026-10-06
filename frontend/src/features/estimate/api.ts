import { apiGet } from '@/shared/api/client'
import type { CompareResult, CostEstimate, MaintenanceMilestones, ReadyEstimate } from './types'
import { getMaintenanceStatus, getVehicleProfile } from '@/features/vehicles/api'

const vehiclePath = (userVehicleId: string) => `/user-vehicles/${encodeURIComponent(userVehicleId)}`

/** API-EST-01 — milestones that have maintenance rules for the vehicle's model. */
export async function getMilestones(userVehicleId: string): Promise<MaintenanceMilestones> {
  const [status, profile] = await Promise.all([getMaintenanceStatus(userVehicleId), getVehicleProfile(userVehicleId)])
  const next = status.nextMilestone
  return { modelId: profile.modelId ?? '', nextOdoMilestone: next?.odoMilestoneKm ?? null,
    milestones: next ? [{ odoMilestone: next.odoMilestoneKm, monthMilestone: next.monthMilestone, itemCount: next.items.length, isNext: true }] : [] }
}

/** API-EST-02 — omitted params ⇒ next milestone / default workshop (BR-1003). */
export async function getCostEstimate(
  userVehicleId: string,
  params: { odoMilestone: number | null; workshopId: string | null; signal?: AbortSignal },
): Promise<CostEstimate> {
  const search = new URLSearchParams()
  if (params.odoMilestone !== null) search.set('odoMilestone', String(params.odoMilestone))
  if (params.workshopId) search.set('workshopId', params.workshopId)
  const query = search.toString()
  const value = await apiGet<CostEstimate | (Omit<ReadyEstimate, 'status' | 'milestone'> & { status: 'SUCCESS'; milestone: { odoMilestoneKm: number; monthMilestone: number; isNext: boolean } })>(`${vehiclePath(userVehicleId)}/cost-estimate${query ? `?${query}` : ''}`, {
    timeoutMs: 10_000,
    signal: params.signal,
  })
  if (value.status === 'NO_RULE') return value
  const legacy = value.status === 'SUCCESS'
  const ready = value as unknown as ReadyEstimate & { milestone: { odoMilestoneKm?: number } }
  return { ...ready, status: 'READY', modelId: ready.modelId ?? '', userVehicleId,
    milestone: { ...ready.milestone, odoMilestone: ready.milestone.odoMilestone ?? ready.milestone.odoMilestoneKm ?? 0,
      monthMilestone: ready.milestone.monthMilestone ?? 12, isNext: ready.milestone.isNext ?? true },
    workshop: { ...ready.workshop, selectedBy: legacy ? (params.workshopId ? 'REQUEST' : 'PREFERRED') : ready.workshop.selectedBy },
    warrantyStatus: legacy ? 'UNKNOWN' : ready.warrantyStatus, coveredCount: ready.coveredCount ?? ready.items.filter(item => item.covered).length,
    hasReferencePrice: legacy ? false : ready.hasReferencePrice, currency: ready.currency ?? 'VND',
    items: ready.items.map(item => ({ ...item, maintenanceRuleId: item.maintenanceRuleId ?? item.itemCode, priceSource: legacy ? 'WORKSHOP_PRICE' : item.priceSource })) }
}

/** API-EST-03 `[Đề xuất — Q-1003]` — same milestone at 2–3 workshops, cheapest first. */
export async function compareEstimates(userVehicleId: string, odoMilestone: number | null, workshopIds: string[]): Promise<CompareResult> {
  const estimates = await Promise.all(workshopIds.map(workshopId => getCostEstimate(userVehicleId, { odoMilestone, workshopId })))
  return { estimates: estimates.filter((estimate): estimate is ReadyEstimate => estimate.status === 'READY').sort((a, b) => a.chargeableTotal - b.chargeableTotal) }
}
