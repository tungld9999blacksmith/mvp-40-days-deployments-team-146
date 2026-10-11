import { apiGet, apiRequest } from '@/shared/api/client'

/** Workshop price list (bao-gia-hai-tang D14) — the prices tier 1 snapshots at booking time. */

export interface PriceRow {
  priceId: string
  price: number
  validFrom: string | null
  validTo: string | null
}

/** One service of the model: its codes are the same service at different milestones. */
export interface PriceItem {
  itemCode: string
  itemCodes: string[]
  itemName: string
  referencePrice: number
  referencePriceMin: number
  /** Valid today for every code, or null: unpriced codes use the reference price. */
  currentPrice: number | null
  pricedCodes: number
  mixedPrices: boolean
  prices: PriceRow[]
}

export interface PriceList {
  modelId: string
  items: PriceItem[]
  pricedCount: number
  models: string[]
  /** "VF8 Plus" per model id when known; other ids show their code. */
  modelNames?: Record<string, string>
}

const BASE = '/workshop-owner/price-list'

export function getPriceList(modelId?: string | null): Promise<PriceList> {
  return apiGet<PriceList>(`${BASE}${modelId ? `?modelId=${encodeURIComponent(modelId)}` : ''}`, { timeoutMs: 10_000 })
}

export async function copyReferencePrices(body: {
  modelId: string
  percent: number
  validFrom?: string | null
}): Promise<{ created: number; skippedItemCodes: string[]; priceList: PriceList }> {
  return (await apiRequest<{ created: number; skippedItemCodes: string[]; priceList: PriceList }>(`${BASE}/copy-reference`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

export async function createPrice(body: {
  modelId: string
  itemCode: string
  price: number
  validFrom?: string | null
  validTo?: string | null
}): Promise<PriceList> {
  return (await apiRequest<PriceList>(BASE, { method: 'POST', body, timeoutMs: 15_000 })).data
}

/** Today's price of a service for all its codes. */
export async function setServicePrice(body: { modelId: string; itemCodes: string[]; price: number }): Promise<PriceList> {
  return (await apiRequest<PriceList>(`${BASE}/set`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

export async function updatePrice(
  priceId: string,
  body: { price: number; validFrom?: string | null; validTo?: string | null },
): Promise<PriceList> {
  return (await apiRequest<PriceList>(`${BASE}/${encodeURIComponent(priceId)}`, { method: 'PUT', body, timeoutMs: 15_000 })).data
}
