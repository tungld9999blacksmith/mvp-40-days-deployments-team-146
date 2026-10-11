import { formatVnd } from '@/features/estimate/utils'
import type { PriceItem } from './api'

/** "350.000 ₫", or "Miễn phí" for 0: the owner sees warranty checks as free, not "0 ₫". */
export function priceText(value: number): string {
  return value === 0 ? 'Miễn phí' : formatVnd(value)
}

/** "350.000 ₫" or "200.000–350.000 ₫" when the milestones differ. */
export function referenceText(item: Pick<PriceItem, 'referencePrice' | 'referencePriceMin'>): string {
  if (item.referencePriceMin === item.referencePrice) return priceText(item.referencePrice)
  return `${formatVnd(item.referencePriceMin).replace(' ₫', '')}–${formatVnd(item.referencePrice)}`
}
