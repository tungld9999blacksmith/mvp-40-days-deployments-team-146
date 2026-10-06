import { formatLicensePlate } from '@/shared/utils/format'
import { cn } from './cn'

/** Licence plate drawn like the real plate: white, ink border, condensed figures. Same in both themes. */
export default function PlateTile({ plate, size = 'md', className }: { plate: string; size?: 'sm' | 'md'; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap bg-white text-[#111820] border-[#111820] font-plate font-semibold leading-none tracking-[0.02em]',
        size === 'md' ? 'text-xl border-2 rounded-md px-2 pt-1 pb-[3px]' : 'text-base border-[1.5px] rounded px-1.5 pt-0.5 pb-px',
        className,
      )}
    >
      {formatLicensePlate(plate)}
    </span>
  )
}
