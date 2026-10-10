import { useEffect, useRef, useState } from 'react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import Checkbox from '@/shared/ui/Checkbox'
import Drawer from '@/shared/ui/Drawer'
import { Field, TextArea, TextInput } from '@/shared/ui/Field'
import MoneyInput from '@/shared/ui/MoneyInput'
import PhotoUploadTile, { PhotoAddTile } from '@/shared/ui/PhotoUploadTile'
import { newId } from '@/shared/utils/id'
import { track } from '@/shared/utils/track'
import { proposeExtra, signLinePhotoUpload, uploadPhoto } from '@/features/booking-lines/api'
import {
  MAX_PHOTOS,
  PHOTO_RULE,
  PHOTO_TYPES,
  REASON_MAX,
  parsePrice,
  photoTileState,
  reasonError,
  validatePhoto,
  type PhotoDraft,
} from '@/features/booking-lines/logic'
import type { LinesView } from '@/features/booking-lines/types'

const ERROR_TEXT: Record<string, string> = {
  STAGE_NOT_ALLOWED: 'Chỉ thêm phát sinh khi đang kiểm tra, bảo dưỡng hoặc chờ phụ tùng.',
  BOOKING_STATUS_INVALID: 'Lịch hẹn không còn ở trạng thái đang làm.',
  PHOTO_INVALID: 'Có ảnh không hợp lệ hoặc đã quá hạn. Xoá ảnh đó rồi tải lại.',
}

/** Design 2A / 8A — the workshop proposes an extra item; the owner decides on the ticket. */
export default function ExtraItemDrawer({
  open,
  bookingId,
  onClose,
  onSent,
}: {
  open: boolean
  bookingId: string
  onClose: () => void
  onSent: (view: LinesView) => void
}) {
  const [name, setName] = useState('')
  const [price, setPrice] = useState('')
  const [reason, setReason] = useState('')
  const [safety, setSafety] = useState(false)
  const [photos, setPhotos] = useState<PhotoDraft[]>([])
  const [touched, setTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const files = useRef(new Map<string, File>())

  useEffect(() => {
    if (!open) return
    setName('')
    setPrice('')
    setReason('')
    setSafety(false)
    setPhotos(current => {
      current.forEach(photo => photo.previewUrl && URL.revokeObjectURL(photo.previewUrl))
      return []
    })
    files.current.clear()
    setTouched(false)
    setServerError(null)
  }, [open])

  const patch = (id: string, change: Partial<PhotoDraft>) =>
    setPhotos(current => current.map(photo => (photo.id === id ? { ...photo, ...change } : photo)))

  async function upload(id: string, file: File) {
    patch(id, { status: 'uploading', progress: 0, error: null, key: null })
    try {
      const target = await signLinePhotoUpload(bookingId, file.type)
      await uploadPhoto(target, file, ratio => patch(id, { progress: ratio }))
      patch(id, { status: 'done', progress: 1, key: target.key })
    } catch {
      patch(id, { status: 'error', error: 'Tải ảnh thất bại' })
    }
  }

  function addFiles(list: File[]) {
    const room = MAX_PHOTOS - photos.length
    for (const file of list.slice(0, room)) {
      const id = newId()
      const invalid = validatePhoto(file)
      const draft: PhotoDraft = {
        id,
        file,
        previewUrl: URL.createObjectURL(file),
        status: invalid ? 'error' : 'uploading',
        progress: 0,
        key: null,
        error: invalid,
      }
      files.current.set(id, file)
      setPhotos(current => [...current, draft])
      if (!invalid) void upload(id, file)
    }
  }

  function remove(id: string) {
    setPhotos(current => {
      const photo = current.find(item => item.id === id)
      if (photo?.previewUrl) URL.revokeObjectURL(photo.previewUrl)
      return current.filter(item => item.id !== id)
    })
    files.current.delete(id)
  }

  const amount = parsePrice(price)
  const nameError = touched && !name.trim() ? 'Nhập tên hạng mục' : null
  const priceError = touched && amount === null ? 'Nhập giá' : null
  const whyError = touched ? reasonError(reason, true) : null
  const tiles = photoTileState(photos)
  const photoRuleError = photos.some(photo => photo.error === PHOTO_RULE) ? PHOTO_RULE : null

  async function submit() {
    setTouched(true)
    if (!name.trim() || amount === null || reasonError(reason, true) || tiles.blockSubmit) return
    setSubmitting(true)
    setServerError(null)
    try {
      const view = await proposeExtra(bookingId, {
        itemName: name.trim(),
        price: amount,
        reason: reason.trim(),
        isSafetyCritical: safety,
        photoKeys: tiles.keys,
      })
      track('booking_line_extra_proposed', { photos: tiles.keys.length, safety })
      onSent(view)
    } catch (failure) {
      const code = isApiError(failure) ? failure.code : ''
      setServerError(ERROR_TEXT[code] ?? (isApiError(failure) ? failure.message : 'Chưa gửi được, bạn thử lại nhé.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Thêm phát sinh" dismissable={!submitting} width="sm:w-[28rem]">
      <form
        className="p-5 space-y-4"
        onSubmit={event => {
          event.preventDefault()
          void submit()
        }}
      >
        <TextInput
          label="Hạng mục"
          required
          value={name}
          maxLength={200}
          onChange={event => setName(event.target.value)}
          error={nameError ?? undefined}
          disabled={submitting}
          placeholder="Thay má phanh trước"
        />
        <Field label="Giá" required error={priceError ?? undefined}>
          {({ describedBy, invalid }) => (
            <MoneyInput value={price} onChange={setPrice} ariaLabel="Giá hạng mục" describedBy={describedBy} invalid={invalid} disabled={submitting} />
          )}
        </Field>
        <TextArea
          label="Lý do (chủ xe sẽ thấy)"
          required
          rows={4}
          maxLength={REASON_MAX}
          value={reason}
          onChange={event => setReason(event.target.value)}
          error={whyError ?? undefined}
          disabled={submitting}
          aside={
            <span className="text-xs text-muted font-mono" aria-hidden>
              {reason.trim().length}/{REASON_MAX}
            </span>
          }
          placeholder="Má phanh trước còn 2mm, dưới mức tối thiểu 3mm."
        />
        <Checkbox
          checked={safety}
          onChange={setSafety}
          disabled={submitting}
          label="Hạng mục an toàn"
          description="Phanh, lốp, hệ thống lái, đèn. Chủ xe phải xác nhận thêm nếu muốn bỏ qua."
        />
        <div>
          <p className="text-sm font-medium text-foreground">
            Ảnh <span className="text-muted font-normal text-xs">(tuỳ chọn, tối đa {MAX_PHOTOS})</span>
          </p>
          <div className="flex flex-wrap gap-3 mt-2">
            {photos.map((photo, index) => (
              <PhotoUploadTile
                key={photo.id}
                label={`Ảnh ${index + 1}`}
                previewUrl={photo.previewUrl}
                status={photo.status}
                progress={photo.progress}
                disabled={submitting}
                onRemove={() => remove(photo.id)}
                onRetry={photo.error === PHOTO_RULE ? undefined : () => void upload(photo.id, files.current.get(photo.id)!)}
              />
            ))}
            {tiles.canAddMore && <PhotoAddTile accept={PHOTO_TYPES.join(',')} disabled={submitting} onFiles={addFiles} />}
          </div>
          <p className={`text-xs mt-2 ${photoRuleError ? 'text-error' : 'text-muted'}`}>{photoRuleError ?? `${PHOTO_RULE}.`}</p>
        </div>
        {serverError && (
          <p role="alert" className="text-sm text-error">
            {serverError}
          </p>
        )}
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Huỷ
          </Button>
          <Button type="submit" loading={submitting} loadingText="Đang gửi…" disabled={Boolean(tiles.blockSubmit)}>
            Gửi chủ xe
          </Button>
        </div>
        {tiles.blockSubmit && <p className="text-xs text-muted text-right">{tiles.blockSubmit}</p>}
      </form>
    </Drawer>
  )
}
