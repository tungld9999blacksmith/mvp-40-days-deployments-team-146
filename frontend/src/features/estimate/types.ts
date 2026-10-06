/** FEAT-COST-001 types — API Spec us-045 (API-EST-01 → 03). */

export interface MilestoneOption {
  odoMilestone: number
  monthMilestone: number
  itemCount: number
  isNext: boolean
}

export interface MaintenanceMilestones {
  modelId: string
  nextOdoMilestone: number | null
  milestones: MilestoneOption[]
}

export type PriceSource = 'WORKSHOP_PRICE' | 'REFERENCE_PRICE'
export type WorkshopSelectedBy = 'REQUEST' | 'PREFERRED' | 'NEAREST'
export type WarrantyStatus = 'ACTIVE' | 'EXPIRED' | 'UNKNOWN'

export interface EstimateItem {
  maintenanceRuleId: string
  itemCode: string
  itemName: string
  covered: boolean
  price: number
  priceSource: PriceSource | null
}

export interface ReadyEstimate {
  status: 'READY'
  userVehicleId: string
  modelId: string
  milestone: { odoMilestone: number; monthMilestone: number; isNext: boolean }
  workshop: { workshopId: string; name: string; selectedBy: WorkshopSelectedBy }
  warrantyStatus: WarrantyStatus
  items: EstimateItem[]
  coveredCount: number
  chargeableTotal: number
  hasReferencePrice: boolean
  currency: string
  estimateLabel: string
  computedAt: string
}

export interface NoRuleEstimate {
  status: 'NO_RULE'
  modelId: string
  milestone: null
  items: []
  chargeableTotal: null
  estimateLabel: string
}

export type CostEstimate = ReadyEstimate | NoRuleEstimate

export type CompareEntry = ReadyEstimate | { workshopId: string; error: { code: string } }

export interface CompareResult {
  estimates: CompareEntry[]
}
