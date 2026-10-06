import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { Check, Copy, Download } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { useToast } from '@/shared/ui/Toast'
import { track } from '@/shared/utils/track'
import { downloadBookingQr } from '../api'

/**
 * us-053 §4.1–4.2 — QR drawn on the client from `qrPayload` (white background in both themes so
 * scanners read it), the booking code in large mono type with "Sao chép", and "Tải QR" (API-BT-02).
 */
export default function TicketQr({ bookingId, code, payload }: { bookingId: string; code: string; payload: string }) {
  const toast = useToast()
  const [src, setSrc] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [downloadable, setDownloadable] = useState(true)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let cancelled = false
    QRCode.toDataURL(payload, { errorCorrectionLevel: 'M', width: 480, margin: 1, color: { dark: '#000000', light: '#ffffff' } })
      .then(url => !cancelled && setSrc(url))
      .catch(() => !cancelled && setSrc(null))
    return () => {
      cancelled = true
    }
  }, [payload])

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.show('Không sao chép được, bạn ghi lại mã giúp mình nhé.', 'warning')
    }
  }

  async function download() {
    setDownloading(true)
    try {
      const blob = await downloadBookingQr(bookingId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `EV-Care-${code}.png`
      link.click()
      URL.revokeObjectURL(url)
      track('qr_downloaded', {})
    } catch (reason) {
      if (isApiError(reason, 'QR_NOT_AVAILABLE')) setDownloadable(false)
      else toast.show('Chưa tải được ảnh QR, bạn thử lại nhé.', 'error')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col items-center text-center">
      <div className="rounded-2xl bg-white p-3 shadow-sm ring-1 ring-black/5">
        {src ? (
          <img src={src} alt={`Mã QR check-in cho lịch hẹn ${code}`} className="w-[220px] h-[220px]" />
        ) : (
          <div className="w-[220px] h-[220px] animate-pulse bg-neutral-100 rounded-lg" aria-hidden />
        )}
      </div>
      <div className="mt-4 flex items-center gap-2">
        <span className="font-mono text-2xl font-semibold tracking-wider text-foreground">{code}</span>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label="Sao chép mã lịch hẹn"
          className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted hover:text-foreground hover:bg-card-hover transition-colors"
        >
          {copied ? <Check className="w-4 h-4 text-emerald" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <p className="text-xs text-muted mt-1">Đưa mã này cho xưởng khi đến nhận xe vào bảo dưỡng.</p>
      {downloadable && (
        <Button variant="ghost" size="sm" className="mt-2" icon={<Download className="w-3.5 h-3.5" />} loading={downloading} onClick={() => void download()}>
          Tải QR
        </Button>
      )}
    </div>
  )
}
