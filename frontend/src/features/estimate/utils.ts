import { formatNumber } from '@/shared/utils/format'

/** 1300000 → "1.300.000 ₫" — never summed on the client (FE §4.3). */
export function formatVnd(value: number): string {
  return `${formatNumber(value)} ₫`
}

/** "Mốc 12.000 km / 12 tháng" */
export function milestoneLabel(odoMilestone: number, monthMilestone: number): string {
  return `Mốc ${formatNumber(odoMilestone)} km / ${monthMilestone} tháng`
}

/** `?odoMilestone=` must be one of API-EST-01 (FE §8); otherwise it is dropped. */
export function validMilestone(value: number | null, options: number[]): number | null {
  return value !== null && options.includes(value) ? value : null
}

export function readNumberParam(value: string | null): number | null {
  return value && /^\d+$/.test(value) ? Number(value) : null
}
