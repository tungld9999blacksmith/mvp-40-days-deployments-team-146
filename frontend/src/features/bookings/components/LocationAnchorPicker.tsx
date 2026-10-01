import { useState, type FormEvent } from 'react'
import { LocateFixed, Search, X } from 'lucide-react'
import Button from '@/shared/ui/Button'
import { TextInput } from '@/shared/ui/Field'
import { useToast } from '@/shared/ui/Toast'
import type { LocationAnchor, NearbyAnchor } from '../types'

function describeAnchor(anchor: NearbyAnchor | null, picked: LocationAnchor): string {
  if (picked?.kind === 'coords') return 'Gần vị trí hiện tại'
  if (picked?.kind === 'query') return `Gần: ${picked.query}`
  if (!anchor) return 'Đang xác định vị trí…'
  if (anchor.source === 'PREFERRED') return 'Gần xưởng ưa thích của bạn'
  if (anchor.source === 'PROFILE') return anchor.province ? `Gần địa chỉ hồ sơ · ${anchor.province}` : 'Gần địa chỉ hồ sơ'
  return anchor.query ?? anchor.province ?? 'Gần vị trí đã chọn'
}

/**
 * FE §4.1 — no anchor ⇒ the backend picks (profile, then preferred workshop);
 * the owner can type a place or use the device location.
 */
export default function LocationAnchorPicker({
  resolved,
  value,
  onChange,
  forceOpen = false,
}: {
  resolved: NearbyAnchor | null
  value: LocationAnchor
  onChange: (anchor: LocationAnchor) => void
  forceOpen?: boolean
}) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(value?.kind === 'query' ? value.query : '')
  const [locating, setLocating] = useState(false)
  const open = editing || forceOpen

  function submit(event: FormEvent) {
    event.preventDefault()
    const query = text.trim()
    if (!query) return
    onChange({ kind: 'query', query })
    setEditing(false)
  }

  function useDeviceLocation() {
    if (!('geolocation' in navigator)) {
      toast.show('Không lấy được vị trí, bạn nhập địa điểm nhé', 'warning')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      position => {
        setLocating(false)
        setEditing(false)
        onChange({ kind: 'coords', lat: position.coords.latitude, lng: position.coords.longitude })
      },
      () => {
        setLocating(false)
        toast.show('Không lấy được vị trí, bạn nhập địa điểm nhé', 'warning')
      },
      { timeout: 10_000, maximumAge: 300_000 },
    )
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-foreground font-medium truncate">{describeAnchor(resolved, value)}</p>
        <div className="flex items-center gap-1 shrink-0">
          {value && (
            <Button variant="ghost" size="sm" icon={<X className="w-3.5 h-3.5" />} onClick={() => onChange(null)}>
              Mặc định
            </Button>
          )}
          {!forceOpen && (
            <Button variant="secondary" size="sm" onClick={() => setEditing(open => !open)}>
              {editing ? 'Đóng' : 'Đổi vị trí'}
            </Button>
          )}
        </div>
      </div>
      {open && (
        <form onSubmit={submit} className="flex flex-col sm:flex-row sm:items-end gap-2">
          <div className="flex-1">
            <TextInput
              label="Địa điểm muốn đặt gần"
              placeholder="Ví dụ: Cầu Giấy, Hà Nội"
              value={text}
              onChange={event => setText(event.target.value)}
              maxLength={200}
            />
          </div>
          <Button type="submit" icon={<Search className="w-4 h-4" />} disabled={!text.trim()}>
            Tìm
          </Button>
          <Button
            type="button"
            variant="secondary"
            icon={<LocateFixed className="w-4 h-4" />}
            loading={locating}
            loadingText="Đang lấy vị trí…"
            onClick={useDeviceLocation}
          >
            Vị trí hiện tại
          </Button>
        </form>
      )}
    </div>
  )
}
