import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Camera, CameraOff, CheckCircle2, Search } from 'lucide-react'
import { isApiError } from '@/shared/api/client'
import Button from '@/shared/ui/Button'
import { Card, InfoRow } from '@/shared/ui/Card'
import { TextInput } from '@/shared/ui/Field'
import Spinner from '@/shared/ui/Spinner'
import { Notice } from '@/shared/ui/States'
import { useToast } from '@/shared/ui/Toast'
import { formatLicensePlate, formatTime } from '@/shared/utils/format'
import { track } from '@/shared/utils/track'
import { dayChip, formatLongDay, slotLabel } from '@/features/bookings/utils'
import { lookupBookingCode, transitionBooking } from '../api'
import type { CodeLookup } from '../types'
import { BOOKING_CODE_PATTERN, codeFromQr } from '../utils'

type ScannerStatus = 'idle' | 'scanning' | 'paused' | 'unavailable'

interface DetectedBarcode {
  rawValue: string
}
interface BarcodeDetectorLike {
  detect: (source: CanvasImageSource) => Promise<DetectedBarcode[]>
}
type BarcodeDetectorCtor = new (options: { formats: string[] }) => BarcodeDetectorLike

/** SCR-803 — scan the ticket QR (BarcodeDetector) or type the code, then confirm check-in (WB-03 → WB-04). */
export default function CheckIn() {
  const toast = useToast()
  const [searchParams] = useSearchParams()
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [scanner, setScanner] = useState<ScannerStatus>('idle')
  const [code, setCode] = useState(searchParams.get('code')?.toUpperCase() ?? '')
  const [codeError, setCodeError] = useState<string | null>(null)
  const [lookup, setLookup] = useState<CodeLookup | null>(null)
  const [lookupMessage, setLookupMessage] = useState<string | null>(null)
  const [looking, setLooking] = useState(false)
  const [checkingIn, setCheckingIn] = useState(false)
  const [method, setMethod] = useState<'qr' | 'manual'>('manual')
  const [announce, setAnnounce] = useState('')

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(item => item.stop())
    streamRef.current = null
  }, [])

  const find = useCallback(async (raw: string, via: 'qr' | 'manual') => {
    const value = raw.trim().toUpperCase()
    if (!BOOKING_CODE_PATTERN.test(value)) {
      setCodeError('Mã lịch hẹn không hợp lệ.')
      return
    }
    setCodeError(null)
    setLooking(true)
    setLookup(null)
    setLookupMessage(null)
    setMethod(via)
    try {
      const result = await lookupBookingCode(value)
      setLookup(result)
      setAnnounce(`Đã tìm thấy lịch hẹn ${value}`)
      track('checkin_scan_result', { eligibility: result.checkInEligibility, method: via })
    } catch (reason) {
      setLookupMessage(isApiError(reason, 'BOOKING_NOT_FOUND') ? 'Không tìm thấy lịch hẹn tại xưởng của bạn.' : 'Chưa tra được mã, bạn thử lại nhé.')
      track('checkin_scan_result', { eligibility: 'NOT_FOUND', method: via })
    } finally {
      setLooking(false)
    }
  }, [])

  // Camera with BarcodeDetector when the browser supports it; otherwise manual input only.
  const startCamera = useCallback(async () => {
    const Detector = (window as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector
    if (!Detector || !navigator.mediaDevices?.getUserMedia) {
      setScanner('unavailable')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setScanner('scanning')
    } catch {
      setScanner('unavailable')
    }
  }, [])

  useEffect(() => {
    void startCamera()
    return stopCamera
  }, [startCamera, stopCamera])

  useEffect(() => {
    if (scanner !== 'scanning') return
    const Detector = (window as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector
    if (!Detector) return
    const detector = new Detector({ formats: ['qr_code'] })
    let stopped = false
    const timer = window.setInterval(async () => {
      const video = videoRef.current
      if (stopped || !video || video.readyState < 2) return
      try {
        const [found] = await detector.detect(video)
        if (found && !stopped) {
          stopped = true
          setScanner('paused')
          const value = codeFromQr(found.rawValue)
          setCode(value)
          void find(value, 'qr')
        }
      } catch {
        // A frame that cannot be decoded is ignored.
      }
    }, 400)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [scanner, find])

  // `/technician/check-in?code=` (from `/c/:code` opened by a workshop owner).
  useEffect(() => {
    const initial = searchParams.get('code')
    if (initial) void find(initial, 'manual')
    // Only once, for the code in the URL.
  }, [])

  async function checkIn() {
    if (!lookup) return
    setCheckingIn(true)
    try {
      await transitionBooking(lookup.bookingId, { action: 'CHECK_IN', expectedStatus: 'CONFIRMED', source: method === 'qr' ? 'QR_SCAN' : 'BOARD' })
      track('booking_transition', { action: 'CHECK_IN', reasonCode: null, source: method === 'qr' ? 'QR_SCAN' : 'BOARD' })
      toast.show('Đã check-in', 'success')
      setAnnounce(`Đã check-in ${lookup.bookingCode ?? ''}`)
      setLookup(null)
      setCode('')
      if (streamRef.current) setScanner('scanning')
    } catch (reason) {
      if (isApiError(reason, 'CHECK_IN_NOT_TODAY')) setLookupMessage(`Lịch hẹn của khách là ngày ${dayChip(lookup.bookingDate).dayMonth}.`)
      else if (isApiError(reason, 'INVALID_STATUS_TRANSITION')) void find(lookup.bookingCode ?? code, method)
      else toast.show('Tạm thời chưa thực hiện được, thử lại nhé.', 'error')
    } finally {
      setCheckingIn(false)
    }
  }

  const resultBody = lookup && (
    <>
      <InfoRow label="Mã" value={lookup.bookingCode ?? '—'} mono />
      <InfoRow label="Khách" value={lookup.customer.fullName} />
      <InfoRow label="Xe" value={`${lookup.vehicle.modelName} · ${formatLicensePlate(lookup.vehicle.licensePlate)}`} />
      <InfoRow label="Giờ hẹn" value={`${slotLabel(lookup.timeSlot)} · ${formatLongDay(lookup.bookingDate)}`} />
    </>
  )

  return (
    <div className="p-4 sm:p-6 xl:p-8 max-w-xl mx-auto space-y-4">
      <Link to="/technician/board" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> Lịch hẹn
      </Link>
      <h1 className="text-2xl font-bold tracking-tight text-foreground">Check-in xe</h1>
      <p aria-live="polite" className="sr-only">
        {announce}
      </p>

      {scanner !== 'unavailable' && (
        <Card className="p-0 overflow-hidden">
          <div className="relative bg-black aspect-square sm:aspect-video">
            <video ref={videoRef} className="w-full h-full object-cover" muted playsInline />
            {scanner === 'scanning' && (
              <div aria-hidden className="absolute inset-[18%] border-2 border-emerald rounded-2xl shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
            )}
            {scanner === 'idle' && (
              <div className="absolute inset-0 flex items-center justify-center text-white/80">
                <Spinner className="w-6 h-6" />
              </div>
            )}
          </div>
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <span className="text-sm text-muted">{scanner === 'scanning' ? 'Đưa mã QR trên vé của khách vào khung.' : 'Tạm dừng quét.'}</span>
            {scanner === 'paused' ? (
              <Button size="sm" variant="secondary" icon={<Camera className="w-4 h-4" />} onClick={() => setScanner('scanning')}>
                Quét tiếp
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                icon={<CameraOff className="w-4 h-4" />}
                onClick={() => {
                  stopCamera()
                  setScanner('unavailable')
                }}
              >
                Tắt camera
              </Button>
            )}
          </div>
        </Card>
      )}
      {scanner === 'unavailable' && (
        <Notice tone="info" title="Nhập mã lịch hẹn">
          Trình duyệt không hỗ trợ quét QR hoặc chưa được cấp quyền camera.{' '}
          <button type="button" className="text-emerald font-medium" onClick={() => void startCamera()}>
            Thử bật camera
          </button>
        </Notice>
      )}

      <Card>
        <form
          className="flex gap-2 items-end"
          onSubmit={event => {
            event.preventDefault()
            void find(code, 'manual')
          }}
        >
          <div className="flex-1">
            <TextInput
              label="Mã lịch hẹn"
              value={code}
              placeholder="EVC-7F3A9C21"
              autoCapitalize="characters"
              className="font-mono uppercase"
              error={codeError ?? undefined}
              onChange={event => setCode(event.target.value.toUpperCase())}
            />
          </div>
          <Button type="submit" icon={<Search className="w-4 h-4" />} loading={looking} className="mb-[1px] h-[42px]">
            Tìm
          </Button>
        </form>
      </Card>

      {looking && (
        <Card className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Đang tìm…
        </Card>
      )}
      {lookupMessage && <Notice tone="warning" title={lookupMessage} />}
      {lookup && (
        <Card className="space-y-3">
          {resultBody}
          {lookup.checkInEligibility === 'ELIGIBLE' && (
            <Button fullWidth size="lg" icon={<CheckCircle2 className="w-4 h-4" />} loading={checkingIn} loadingText="Đang check-in…" onClick={() => void checkIn()}>
              Xác nhận check-in
            </Button>
          )}
          {lookup.checkInEligibility === 'NOT_TODAY' && <Notice tone="warning" title={`Lịch hẹn của khách là ngày ${dayChip(lookup.bookingDate).dayMonth}.`} />}
          {lookup.checkInEligibility === 'ALREADY_CHECKED_IN' && (
            <Notice
              tone="success"
              title={`Đã check-in${lookup.checkedInAt ? ` lúc ${formatTime(lookup.checkedInAt)}` : ''}.`}
              action={
                <Link to={`/technician/board/${encodeURIComponent(lookup.bookingId)}`} className="text-sm text-emerald font-medium">
                  Xem chi tiết
                </Link>
              }
            />
          )}
          {lookup.checkInEligibility === 'NOT_CONFIRMED' && <Notice tone="error" title="Lịch hẹn không ở trạng thái có thể check-in." />}
        </Card>
      )}
    </div>
  )
}
