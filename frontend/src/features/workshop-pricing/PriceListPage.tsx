import { useCallback, useEffect, useState } from 'react'
import { Copy, Tags } from 'lucide-react'
import { isApiError, type ApiError } from '@/shared/api/client'
import Badge from '@/shared/ui/Badge'
import Button from '@/shared/ui/Button'
import { Card, CardHeader } from '@/shared/ui/Card'
import { SelectInput, TextInput } from '@/shared/ui/Field'
import MoneyInput from '@/shared/ui/MoneyInput'
import { SkeletonCard } from '@/shared/ui/Skeleton'
import { EmptyState, ErrorState } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatDate } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { formatVnd } from '@/features/estimate/utils'
import { parsePrice } from '@/features/booking-lines/logic'
import { copyReferencePrices, getPriceList, setServicePrice, type PriceItem, type PriceList } from './api'

const ERROR_TEXT: Record<string, string> = {
  PRICE_PERIOD_OVERLAP: 'Hạng mục này đã có giá trong cùng khoảng thời gian.',
  WORKSHOP_INACTIVE: 'Xưởng đang tạm ngưng, chưa lưu được.',
}

function validity(item: PriceItem): string | null {
  const row = item.prices.find(p => p.price === item.currentPrice && p.validTo)
  return row?.validTo ? `Hiệu lực đến ${formatDate(row.validTo)}` : null
}

/** "350.000 ₫" or "200.000–350.000 ₫" when the milestones differ. */
function referenceText(item: PriceItem): string {
  return item.referencePriceMin === item.referencePrice
    ? formatVnd(item.referencePrice)
    : `${formatVnd(item.referencePriceMin).replace(' ₫', '')}–${formatVnd(item.referencePrice)}`
}

/** Same service at several milestones (QA ISSUE-003): one row, one price for all its codes. */
function milestonesText(item: PriceItem): string | null {
  return item.itemCodes.length > 1 ? `${item.itemCodes.length} mốc` : null
}

/** Bảng giá (D14): my price per item next to the reference; booked prices are snapshotted. */
export default function PriceListPage() {
  const toast = useToast()
  const [list, setList] = useState<PriceList | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [percent, setPercent] = useState('0')
  const [copying, setCopying] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback((modelId?: string | null) => {
    setError(null)
    return getPriceList(modelId)
      .then(setList)
      .catch((reason: unknown) => setError(isApiError(reason) ? reason : null))
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function fail(reason: unknown) {
    const code = isApiError(reason) ? reason.code : ''
    toast.show(ERROR_TEXT[code] ?? 'Tạm thời chưa lưu được, thử lại nhé.', 'error')
  }

  async function copy() {
    if (!list) return
    const value = Number(percent)
    if (!Number.isFinite(value) || value < -50 || value > 200) return toast.show('Tỉ lệ từ -50% đến 200%.', 'warning')
    setCopying(true)
    try {
      const result = await copyReferencePrices({ modelId: list.modelId, percent: value })
      setList(result.priceList)
      track('price_list_copied', { percent: value, created: result.created })
      toast.show(result.created ? `Đã tạo ${result.created} giá. Sửa từng dòng nếu cần.` : 'Mọi hạng mục đã có giá.', 'success')
    } catch (reason) {
      fail(reason)
    } finally {
      setCopying(false)
    }
  }

  async function save(item: PriceItem) {
    if (!list) return
    const price = parsePrice(draft)
    if (price === null) return
    setSaving(true)
    try {
      setList(await setServicePrice({ modelId: list.modelId, itemCodes: item.itemCodes, price }))
      setEditing(null)
      toast.show('Đã lưu giá.', 'success')
    } catch (reason) {
      fail(reason)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Bảng giá</h1>
        <p className="text-sm text-muted mt-1">
          Giá chủ xe thấy và chốt khi đặt lịch. Hạng mục chưa có giá dùng giá tham khảo của hãng và bạn xác nhận khi nhận xe.
        </p>
      </div>

      {!list ? (
        error ? (
          <Card>
            {isApiError(error, 'MODEL_NOT_FOUND') ? (
              <EmptyState icon={<Tags className="w-5 h-5" />} title="Chưa có lịch bảo dưỡng nào để đặt giá" />
            ) : (
              <ErrorState title="Không tải được bảng giá." traceId={error.traceId} onRetry={() => void load()} />
            )}
          </Card>
        ) : (
          <SkeletonCard lines={6} />
        )
      ) : (
        <>
          <Card className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-44">
                <SelectInput label="Dòng xe" value={list.modelId} onChange={event => void load(event.target.value)}>
                  {list.models.map(model => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </SelectInput>
              </div>
              <Badge tone={list.pricedCount === list.items.length ? 'success' : 'warning'}>
                Đã có giá {list.pricedCount}/{list.items.length} hạng mục
              </Badge>
            </div>
            <div className="flex flex-wrap items-end gap-3 pt-3 border-t border-border">
              <div className="w-36">
                <TextInput label="Giá tham khảo ±" inputMode="numeric" value={percent} onChange={event => setPercent(event.target.value.replace(/[^\d-]/g, ''))} aside={<span className="text-xs text-muted">%</span>} />
              </div>
              <Button variant="secondary" icon={<Copy className="w-4 h-4" />} loading={copying} onClick={() => void copy()}>
                Sao chép cho hạng mục chưa có giá
              </Button>
            </div>
          </Card>

          <Card className="p-0 overflow-hidden">
            <div className="px-5 pt-4">
              <CardHeader title={`Hạng mục · ${list.modelId}`} />
            </div>
            <ul className="divide-y divide-border">
              {list.items.map(item => (
                <li key={item.itemCode} className="px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-foreground">{item.itemName}</p>
                    <p className="text-xs text-muted">
                      {milestonesText(item) && `${milestonesText(item)} · `}Tham khảo <span className="font-mono">{referenceText(item)}</span>
                      {validity(item) && ` · ${validity(item)}`}
                    </p>
                  </div>
                  {editing === item.itemCode ? (
                    <div className="flex items-center gap-2">
                      <MoneyInput value={draft} onChange={setDraft} ariaLabel={`Giá của xưởng cho ${item.itemName}`} placeholder={item.referencePrice} disabled={saving} />
                      <Button size="sm" variant="ghost" onClick={() => setEditing(null)} disabled={saving}>
                        Huỷ
                      </Button>
                      <Button size="sm" loading={saving} disabled={parsePrice(draft) === null} onClick={() => void save(item)}>
                        Lưu
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 sm:justify-end">
                      {item.currentPrice !== null ? (
                        <span className="font-mono text-sm text-foreground">{formatVnd(item.currentPrice)}</span>
                      ) : item.pricedCodes > 0 ? (
                        <span className="text-xs text-warning">
                          {item.mixedPrices ? 'Giá khác nhau giữa các mốc' : `Có giá ${item.pricedCodes}/${item.itemCodes.length} mốc`}
                        </span>
                      ) : (
                        <span className="text-xs text-warning">Chưa có giá</span>
                      )}
                      <Button
                        size="sm"
                        variant="secondary"
                        aria-label={`${item.currentPrice !== null ? 'Sửa giá' : 'Đặt giá'} ${item.itemName}`}
                        onClick={() => {
                          setEditing(item.itemCode)
                          setDraft(String(item.currentPrice ?? item.referencePrice))
                        }}
                      >
                        {item.currentPrice !== null ? 'Sửa' : 'Đặt giá'}
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  )
}
