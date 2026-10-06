/**
 * Maintenance rules, workshop prices and the deterministic estimate (us-045 BR-1001/BR-1004).
 * Shared by the estimate and booking-ticket mocks so every screen shows the same numbers.
 */
import { fold, getDb, hash01, isDemo, nowIso, type MockVehicle, type MockWorkshop } from './db'

interface RuleItem {
  itemCode: string
  itemName: string
  coveredByWarranty: boolean
  referencePrice: number
  /** Applies at milestones that are a multiple of this many km. */
  everyKm: number
}

const RULES: RuleItem[] = [
  { itemCode: 'BATTERY_CHECK', itemName: 'Kiểm tra pin cao áp', coveredByWarranty: true, referencePrice: 0, everyKm: 12_000 },
  { itemCode: 'SOFTWARE_UPDATE', itemName: 'Cập nhật phần mềm xe', coveredByWarranty: true, referencePrice: 0, everyKm: 12_000 },
  { itemCode: 'BRAKE_INSPECTION', itemName: 'Kiểm tra hệ thống phanh', coveredByWarranty: false, referencePrice: 300_000, everyKm: 12_000 },
  { itemCode: 'TIRE_ROTATION', itemName: 'Đảo lốp, kiểm tra áp suất lốp', coveredByWarranty: false, referencePrice: 200_000, everyKm: 12_000 },
  { itemCode: 'CABIN_FILTER_REPLACE', itemName: 'Thay lọc gió điều hoà', coveredByWarranty: false, referencePrice: 450_000, everyKm: 12_000 },
  { itemCode: 'COOLANT_CHECK', itemName: 'Kiểm tra nước làm mát', coveredByWarranty: false, referencePrice: 200_000, everyKm: 12_000 },
  { itemCode: 'BRAKE_FLUID_REPLACE', itemName: 'Thay dầu phanh', coveredByWarranty: false, referencePrice: 350_000, everyKm: 24_000 },
  { itemCode: 'AC_SERVICE', itemName: 'Bảo dưỡng hệ thống điều hoà', coveredByWarranty: false, referencePrice: 600_000, everyKm: 36_000 },
  { itemCode: 'COOLANT_REPLACE', itemName: 'Thay nước làm mát pin', coveredByWarranty: false, referencePrice: 900_000, everyKm: 48_000 },
  { itemCode: 'WIPER_REPLACE', itemName: 'Thay lưỡi gạt mưa', coveredByWarranty: false, referencePrice: 250_000, everyKm: 48_000 },
]

const MILESTONE_STEP_KM = 12_000
const MILESTONE_COUNT = 8
/** Models without any rule — demo of the `NO_RULE` state (FF BR-1009). */
const MODELS_WITHOUT_RULES = ['VF3']

export interface MilestoneOption {
  odoMilestone: number
  monthMilestone: number
  itemCount: number
  isNext: boolean
}

export function hasRules(vehicle: MockVehicle): boolean {
  return !MODELS_WITHOUT_RULES.includes(vehicle.modelId.toUpperCase())
}

function ruleItems(odoMilestone: number): RuleItem[] {
  return RULES.filter(rule => odoMilestone % rule.everyKm === 0)
}

export function milestonesFor(vehicle: MockVehicle): MilestoneOption[] {
  if (!hasRules(vehicle)) return []
  return Array.from({ length: MILESTONE_COUNT }, (_, index) => {
    const odoMilestone = (index + 1) * MILESTONE_STEP_KM
    return {
      odoMilestone,
      monthMilestone: odoMilestone / 1000,
      itemCount: ruleItems(odoMilestone).length,
      isNext: odoMilestone === vehicle.nextOdoMilestone,
    }
  })
}

export function isValidMilestone(vehicle: MockVehicle, odoMilestone: number): boolean {
  return milestonesFor(vehicle).some(item => item.odoMilestone === odoMilestone)
}

function roundPrice(value: number): number {
  return Math.round(value / 10_000) * 10_000
}

/** Workshop price of an item; `null` when the workshop has no price ⇒ reference price (BR-1004). */
function workshopPrice(workshopId: string, itemCode: string, referencePrice: number): number | null {
  if (hash01(`${workshopId}:${itemCode}:has`) < 0.2) return null
  return roundPrice(referencePrice * (0.85 + 0.35 * hash01(`${workshopId}:${itemCode}`)))
}

export interface EstimateItem {
  maintenanceRuleId: string
  itemCode: string
  itemName: string
  covered: boolean
  price: number
  priceSource: 'WORKSHOP_PRICE' | 'REFERENCE_PRICE' | null
}

export interface CostEstimate {
  status: 'READY'
  userVehicleId: string
  modelId: string
  milestone: { odoMilestone: number; monthMilestone: number; isNext: boolean }
  workshop: { workshopId: string; name: string; selectedBy: 'REQUEST' | 'PREFERRED' | 'NEAREST' }
  warrantyStatus: 'ACTIVE' | 'EXPIRED' | 'UNKNOWN'
  items: EstimateItem[]
  coveredCount: number
  chargeableTotal: number
  hasReferencePrice: boolean
  currency: 'VND'
  estimateLabel: 'Chi phí ước tính'
  computedAt: string
}

export function estimate(
  vehicle: MockVehicle,
  odoMilestone: number,
  workshop: MockWorkshop,
  selectedBy: CostEstimate['workshop']['selectedBy'],
): CostEstimate {
  const realNames = odoMilestone === vehicle.nextOdoMilestone ? vehicle.nextItems : []
  const underWarranty = vehicle.warrantyStatus !== 'EXPIRED'
  const items: EstimateItem[] = ruleItems(odoMilestone).map(rule => {
    const real = realNames.find(item => item.itemCode === rule.itemCode)
    const covered = underWarranty && (real ? real.covered : rule.coveredByWarranty)
    const price = covered ? null : workshopPrice(workshop.workshopId, rule.itemCode, rule.referencePrice)
    return {
      maintenanceRuleId: `${vehicle.modelId}-${odoMilestone}-${rule.itemCode}`,
      itemCode: rule.itemCode,
      itemName: real?.itemName ?? rule.itemName,
      covered,
      price: covered ? 0 : price ?? rule.referencePrice,
      priceSource: covered ? null : price === null ? 'REFERENCE_PRICE' : 'WORKSHOP_PRICE',
    }
  })
  const chargeable = items.filter(item => !item.covered)
  return {
    status: 'READY',
    userVehicleId: vehicle.userVehicleId,
    modelId: vehicle.modelId,
    milestone: { odoMilestone, monthMilestone: odoMilestone / 1000, isNext: odoMilestone === vehicle.nextOdoMilestone },
    workshop: { workshopId: workshop.workshopId, name: workshop.name, selectedBy },
    warrantyStatus: vehicle.warrantyStatus,
    items,
    coveredCount: items.length - chargeable.length,
    chargeableTotal: chargeable.reduce((sum, item) => sum + item.price, 0),
    hasReferencePrice: chargeable.some(item => item.priceSource === 'REFERENCE_PRICE'),
    currency: 'VND',
    estimateLabel: 'Chi phí ước tính',
    computedAt: nowIso(),
  }
}

/** Default workshop (BR-1003): preferred, then the nearest known one. */
export function defaultWorkshop(): { workshop: MockWorkshop; selectedBy: 'PREFERRED' | 'NEAREST' } | null {
  const db = getDb()
  const active = db.workshops.filter(workshop => workshop.active && !workshop.demo)
  const preferred = active.find(workshop => workshop.isPreferred)
  if (preferred) return { workshop: preferred, selectedBy: 'PREFERRED' }
  // Demo: "nearest" = first workshop in the owner's province.
  const province = isDemo() && db.account.location ? fold(db.account.location.province) : null
  const nearest = (province && active.find(workshop => fold(workshop.region) === province)) || active[0]
  return nearest ? { workshop: nearest, selectedBy: 'NEAREST' } : null
}

/** Items of a milestone without prices — booking ticket "Hạng mục" (us-053 BR-1202). */
export function milestoneItems(vehicle: MockVehicle | null, odoMilestone: number | null): { itemName: string; covered: boolean }[] {
  if (odoMilestone === null) return []
  const real = vehicle && odoMilestone === vehicle.nextOdoMilestone ? vehicle.nextItems : []
  return ruleItems(odoMilestone).map(rule => {
    const known = real.find(item => item.itemCode === rule.itemCode)
    return { itemName: known?.itemName ?? rule.itemName, covered: known ? known.covered : rule.coveredByWarranty }
  })
}

/** Items of a milestone with their codes, as the maintenance status returns them (us-017, us-061 card). */
export function milestoneRuleItems(vehicle: MockVehicle, odoMilestone: number): { itemCode: string; itemName: string; isCoveredByWarranty: boolean }[] {
  const underWarranty = vehicle.warrantyStatus !== 'EXPIRED'
  return ruleItems(odoMilestone).map(rule => ({
    itemCode: rule.itemCode,
    itemName: rule.itemName,
    isCoveredByWarranty: underWarranty && rule.coveredByWarranty,
  }))
}
