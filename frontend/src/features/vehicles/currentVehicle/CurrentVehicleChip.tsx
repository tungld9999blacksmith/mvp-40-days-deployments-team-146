import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Car, ChevronDown } from 'lucide-react'
import Button from '@/shared/ui/Button'
import Dialog from '@/shared/ui/Dialog'
import { cn } from '@/shared/ui/cn'
import { formatLicensePlate } from '@/shared/utils/format'
import { useCurrentVehicle } from './CurrentVehicleContext'
import { isBookingInProgress, selectVehiclePath } from './resolve'

/** Topbar: the plate of the vehicle on screen; opens the picker. Hidden for owners with one vehicle. */
export default function CurrentVehicleChip() {
  const { vehicles, current } = useCurrentVehicle()
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const [confirmOpen, setConfirmOpen] = useState(false)

  if (!current || !vehicles || vehicles.length < 2) return null
  const plate = formatLicensePlate(current.licensePlate)

  const openPicker = () => {
    setConfirmOpen(false)
    navigate(selectVehiclePath(pathname + search))
  }

  return (
    <>
      <button
        type="button"
        onClick={() => (isBookingInProgress(pathname, search) ? setConfirmOpen(true) : openPicker())}
        aria-label={`Đổi xe, đang xem ${plate}`}
        className={cn(
          'h-9 shrink-0 whitespace-nowrap inline-flex items-center gap-1.5 rounded-full bg-card/60 border border-border px-2.5 sm:px-3 text-foreground',
          'hover:bg-card-hover hover:border-foreground/15 transition-colors',
        )}
      >
        <Car className="hidden sm:block w-4 h-4 text-muted" aria-hidden />
        <span className="font-plate text-sm font-semibold tracking-wide">{plate}</span>
        {/* Phones: the plate alone, so the page title keeps its room in the topbar. */}
        <ChevronDown className="hidden sm:block w-3.5 h-3.5 text-muted" aria-hidden />
      </button>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Đổi xe?"
        description="Đổi xe sẽ huỷ lịch đang đặt dở. Tiếp tục?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Ở lại
            </Button>
            <Button onClick={openPicker}>Đổi xe</Button>
          </>
        }
      />
    </>
  )
}
