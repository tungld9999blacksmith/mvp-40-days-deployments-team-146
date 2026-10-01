/** FEAT-VEH-001 types — backend `modules/user_vehicle/schemas.py`, API-SPEC-VEH-001 §C. */

export type DueStatus = 'NORMAL' | 'DUE_SOON' | 'OVERDUE' | 'UNKNOWN'
export type DueReason = 'KM' | 'TIME' | 'BOTH'
export type CalculationBasis = 'KM_AND_TIME' | 'TIME_ONLY'
export type UnknownReason = 'OEM_DATA_NOT_SYNCED' | 'NO_MAINTENANCE_RULE'

export interface Odometer {
  odoKm: number
  recordedAt: string
  isStale: boolean
  dataSource: string
}

export interface MilestoneItem {
  itemCode: string
  itemName: string
  isCoveredByWarranty: boolean
}

export interface NextMilestone {
  odoMilestoneKm: number
  monthMilestone: number
  /** English label for code / AI — the UI builds its own Vietnamese text. */
  label: string
  dueDate: string
  isRecurring: boolean
  items: MilestoneItem[]
}

export interface MaintenanceStatus {
  userVehicleId: string
  dueStatus: DueStatus | string
  dueReason: DueReason | null
  calculationBasis: CalculationBasis | null
  unknownReason: UnknownReason | string | null
  nextMilestone: NextMilestone | null
  remainingKm: number | null
  remainingDays: number | null
  odometer: Odometer | null
  lastService: { type: string; date: string; odoKm: number | null } | null
  thresholds: { dueSoonKm: number; dueSoonDays: number }
  oemSyncedAt: string | null
  calculatedAt: string
}

export interface VehicleSummary {
  userVehicleId: string
  modelName: string | null
  trim: string | null
  licensePlate: string
  color: string | null
}

export interface Warranty {
  component: string
  startDate: string
  endDate: string
  kmLimit: number | null
  isActive: boolean
}

export interface VehicleProfile {
  userVehicleId: string
  vinMasked: string
  licensePlate: string
  modelId: string | null
  modelName: string | null
  trim: string | null
  color: string | null
  productionYear: number | null
  manufactureDate: string | null
  batteryCapacityKwh: number | string | null
  motorPowerKw: number | string | null
  warranties: Warranty[]
  odometer: Odometer | null
  lastService: { serviceDate: string; odoKm: number | null; source: string; centerName: string | null } | null
  oemSyncedAt: string | null
}
