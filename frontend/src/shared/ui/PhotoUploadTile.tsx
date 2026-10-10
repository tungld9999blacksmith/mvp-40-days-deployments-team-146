import { useId, useRef } from 'react'
import { Camera, RotateCcw, X } from 'lucide-react'
import { cn } from './cn'

/** Progress ring drawn around the preview while the file uploads. */
function ProgressRing({ ratio }: { ratio: number }) {
  const r = 14
  const c = 2 * Math.PI * r
  return (
    <svg viewBox="0 0 32 32" className="w-8 h-8 -rotate-90" aria-hidden>
      <circle cx="16" cy="16" r={r} fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <circle cx="16" cy="16" r={r} fill="none" stroke="currentColor" strokeWidth="3" strokeDasharray={c} strokeDashoffset={c * (1 - ratio)} strokeLinecap="round" />
    </svg>
  )
}

/**
 * 72px photo tile (design 8A): a preview with a progress ring while uploading,
 * a red border with "Tải lại" / "Xoá" on error. `PhotoUploadTile.Add` opens the
 * camera on phones (`capture`).
 */
export default function PhotoUploadTile({
  previewUrl,
  status,
  progress,
  label,
  onRetry,
  onRemove,
  disabled,
}: {
  previewUrl: string | null
  status: 'uploading' | 'done' | 'error'
  progress: number
  /** Alt text / accessible name, e.g. "Ảnh 1". */
  label: string
  onRetry?: () => void
  onRemove: () => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={cn(
          'relative w-[72px] h-[72px] rounded-xl overflow-hidden border bg-card',
          status === 'error' ? 'border-error' : 'border-border',
        )}
      >
        {previewUrl ? <img src={previewUrl} alt={label} className="w-full h-full object-cover" /> : <span className="sr-only">{label}</span>}
        {status === 'uploading' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 text-white" role="progressbar" aria-label={`Đang tải ${label}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
            <ProgressRing ratio={progress} />
          </div>
        )}
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          aria-label={`Xoá ${label}`}
          className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 disabled:opacity-50"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {status === 'error' && onRetry && (
        <button type="button" onClick={onRetry} disabled={disabled} className="inline-flex items-center gap-1 text-xs text-error hover:underline">
          <RotateCcw className="w-3 h-3" /> Tải lại
        </button>
      )}
    </div>
  )
}

/** The "add photo" tile; hidden by the caller once three photos are attached. */
export function PhotoAddTile({ onFiles, disabled, accept }: { onFiles: (files: File[]) => void; disabled?: boolean; accept: string }) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <label
      htmlFor={inputId}
      className={cn(
        'w-[72px] h-[72px] rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-1 text-xs text-muted cursor-pointer hover:text-foreground hover:bg-card-hover transition-colors',
        'focus-within:ring-4 focus-within:ring-emerald/25',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <Camera className="w-5 h-5" aria-hidden />
      Thêm ảnh
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        capture="environment"
        multiple
        disabled={disabled}
        className="sr-only"
        onChange={event => {
          const files = Array.from(event.target.files ?? [])
          if (inputRef.current) inputRef.current.value = ''
          if (files.length) onFiles(files)
        }}
      />
    </label>
  )
}
