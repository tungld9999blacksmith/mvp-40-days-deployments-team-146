/** us-045 API-EST-01 → 03 — maintenance milestones and the deterministic cost estimate. */
import { defaultWorkshop, estimate, hasRules, isValidMilestone, milestonesFor } from './catalog'
import { fail, ok, route } from './core'
import { getDb, type MockVehicle, type MockWorkshop } from './db'

const GROUP = 'estimate'

function vehicleOf(id: string): MockVehicle | null {
  return getDb().vehicles.find(item => item.userVehicleId === id) ?? null
}

const vehicleNotFound = () => fail(404, 'VEHICLE_NOT_FOUND', 'Không tìm thấy xe.')

type Resolved =
  | { kind: 'error'; result: ReturnType<typeof fail> }
  | { kind: 'no-rule' }
  | { kind: 'ok'; milestone: number }

function resolveMilestone(vehicle: MockVehicle, raw: string | null): Resolved {
  if (!hasRules(vehicle)) return { kind: 'no-rule' }
  const valid = milestonesFor(vehicle).map(item => item.odoMilestone)
  if (raw) {
    const value = Number(raw)
    if (!Number.isInteger(value)) return { kind: 'error', result: fail(400, 'INVALID_REQUEST', 'odoMilestone không hợp lệ.') }
    if (!isValidMilestone(vehicle, value)) {
      return {
        kind: 'error',
        result: fail(422, 'MILESTONE_NOT_FOUND', 'Mốc bảo dưỡng không có trong định mức của xe.', { validMilestones: valid }),
      }
    }
    return { kind: 'ok', milestone: value }
  }
  if (vehicle.nextOdoMilestone === null || !valid.includes(vehicle.nextOdoMilestone)) {
    return { kind: 'error', result: fail(422, 'MILESTONE_REQUIRED', 'Cần chọn mốc bảo dưỡng.', { validMilestones: valid }) }
  }
  return { kind: 'ok', milestone: vehicle.nextOdoMilestone }
}

function workshopById(id: string): MockWorkshop | null {
  const workshop = getDb().workshops.find(item => item.workshopId === id)
  return workshop && workshop.active ? workshop : null
}

const NO_RULE = (vehicle: MockVehicle) =>
  ok({ status: 'NO_RULE', modelId: vehicle.modelId, milestone: null, items: [], chargeableTotal: null, estimateLabel: 'Chi phí ước tính' })

export function registerEstimateRoutes() {
  route(GROUP, 'GET', '/user-vehicles/:id/maintenance-milestones', req => {
    const vehicle = vehicleOf(req.params.id)
    if (!vehicle) return vehicleNotFound()
    return ok({ modelId: vehicle.modelId, nextOdoMilestone: hasRules(vehicle) ? vehicle.nextOdoMilestone : null, milestones: milestonesFor(vehicle) })
  })

  route(GROUP, 'GET', '/user-vehicles/:id/cost-estimate', req => {
    const vehicle = vehicleOf(req.params.id)
    if (!vehicle) return vehicleNotFound()
    const milestone = resolveMilestone(vehicle, req.query.get('odoMilestone'))
    if (milestone.kind === 'no-rule') return NO_RULE(vehicle)
    if (milestone.kind === 'error') return milestone.result
    const workshopId = req.query.get('workshopId')
    if (workshopId) {
      const workshop = workshopById(workshopId)
      if (!workshop) return fail(404, 'WORKSHOP_NOT_FOUND', 'Xưởng hiện không nhận khách.')
      return ok(estimate(vehicle, milestone.milestone, workshop, 'REQUEST'))
    }
    const fallback = defaultWorkshop()
    if (!fallback) return fail(422, 'WORKSHOP_REQUIRED', 'Chưa xác định được xưởng.')
    return ok(estimate(vehicle, milestone.milestone, fallback.workshop, fallback.selectedBy))
  })

  route(GROUP, 'GET', '/user-vehicles/:id/cost-estimate/compare', req => {
    const vehicle = vehicleOf(req.params.id)
    if (!vehicle) return vehicleNotFound()
    const ids = [...new Set(req.query.getAll('workshopIds'))]
    if (ids.length < 2 || ids.length > 3) return fail(400, 'INVALID_REQUEST', 'Chọn từ 2 đến 3 xưởng để so sánh.', { field: 'workshopIds' })
    const milestone = resolveMilestone(vehicle, req.query.get('odoMilestone'))
    if (milestone.kind === 'no-rule') return NO_RULE(vehicle)
    if (milestone.kind === 'error') return milestone.result
    const results = ids.map(id => {
      const workshop = workshopById(id)
      return workshop ? estimate(vehicle, milestone.milestone, workshop, 'REQUEST') : { workshopId: id, error: { code: 'WORKSHOP_NOT_FOUND' } }
    })
    results.sort((a, b) => {
      const left = 'chargeableTotal' in a ? a.chargeableTotal : Number.POSITIVE_INFINITY
      const right = 'chargeableTotal' in b ? b.chargeableTotal : Number.POSITIVE_INFINITY
      return left - right
    })
    return ok({ odoMilestone: milestone.milestone, estimates: results })
  })
}
