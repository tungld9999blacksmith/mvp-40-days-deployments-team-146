import { useTween } from '@/shared/hooks/useTween'
import { cn } from './cn'

export type GaugeTone = 'green' | 'amber' | 'red' | 'off'

// 240° sweep from lower-left to lower-right on a 200 × 184 box (DESIGN.md "Gauge").
const CX = 100
const CY = 100
const R = 82
const START = 150
const SWEEP = 240
const TICKS = 40

const FILL: Record<GaugeTone, string> = {
  green: 'var(--color-banner-accent)',
  amber: 'var(--color-banner-alert)',
  red: 'var(--color-banner-danger)',
  off: 'transparent',
}

function point(radius: number, deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180
  return [CX + radius * Math.cos(rad), CY + radius * Math.sin(rad)]
}

function arc(from: number, to: number): string {
  const a0 = START + SWEEP * from
  const a1 = START + SWEEP * to
  const [x0, y0] = point(R, a0)
  const [x1, y1] = point(R, a1)
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${R} ${R} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

const TRACK = arc(0, 1)
const ZONE = arc(0.9, 1)
const TICK_LINES = Array.from({ length: TICKS + 1 }, (_, i) => {
  const f = i / TICKS
  const major = i % 10 === 0
  const deg = START + SWEEP * f
  const [x1, y1] = point(R + 9, deg)
  const [x2, y2] = point(R + (major ? 16 : 12), deg)
  return { key: i, x1, y1, x2, y2, major, zone: f >= 0.9 }
})

/**
 * Instrument gauge on ink: arc drawn to scale (`fraction` 0–1, null = empty track), figure and caption in
 * the centre. The SVG is decorative; the figure, unit and caption are the accessible text.
 */
export default function Gauge({
  fraction,
  tone,
  value,
  unit,
  caption,
  ends,
  className,
}: {
  fraction: number | null
  tone: GaugeTone
  value: string | null
  unit: string
  caption: string
  ends: [string, string] | null
  className?: string
}) {
  // Arc and end cap move together along the arc (the self-test sweep, or a new reading).
  const shown = useTween(fraction === null ? 0 : Math.min(1, Math.max(0, fraction)))
  const [capX, capY] = point(R, START + SWEEP * shown)
  return (
    <div className={cn('relative w-full max-w-[236px] aspect-[200/184] justify-self-center', className)}>
      <svg viewBox="0 0 200 184" className="absolute inset-0 w-full h-full overflow-visible" aria-hidden>
        {TICK_LINES.map(tick => (
          <line
            key={tick.key}
            x1={tick.x1.toFixed(2)}
            y1={tick.y1.toFixed(2)}
            x2={tick.x2.toFixed(2)}
            y2={tick.y2.toFixed(2)}
            stroke={tick.zone ? 'var(--color-banner-alert)' : 'var(--color-lamp-off)'}
            strokeOpacity={tick.zone ? 0.7 : 1}
            strokeWidth={tick.major ? 2 : 1}
            strokeLinecap="round"
          />
        ))}
        <path d={TRACK} fill="none" stroke="var(--color-banner-raised)" strokeWidth={10} strokeLinecap="round" />
        <path d={ZONE} fill="none" stroke="var(--color-banner-alert)" strokeOpacity={0.22} strokeWidth={10} />
        {fraction !== null && (
          <>
            <path
              d={TRACK}
              pathLength={100}
              fill="none"
              stroke={FILL[tone]}
              strokeWidth={10}
              strokeLinecap="round"
              strokeDasharray={`${(shown * 100).toFixed(2)} 100`}
            />
            <circle
              cx={capX.toFixed(2)}
              cy={capY.toFixed(2)}
              r={5.5}
              fill="var(--color-banner-foreground)"
              stroke="var(--color-banner)"
              strokeWidth={2.5}
            />
          </>
        )}
      </svg>
      <div className="absolute inset-x-0 top-[33%] flex flex-col items-center text-center">
        <span
          className={cn(
            'font-plate font-semibold leading-none text-[28px] @min-[45rem]:text-[38px]',
            tone === 'amber' && 'text-banner-alert',
            tone === 'red' && 'text-banner-danger',
          )}
        >
          {value ?? '—'}
        </span>
        <span className="mt-1 text-xs text-banner-muted">{unit}</span>
        <span className="mt-1.5 font-mono text-[9.5px] tracking-[0.03em] @min-[45rem]:text-[10.5px] @min-[45rem]:tracking-[0.08em] uppercase text-banner-muted">
          {caption}
        </span>
      </div>
      {ends && (
        <div className="absolute inset-x-[6%] bottom-[2%] flex justify-between font-plate text-[11px] text-banner-muted">
          <span>{ends[0]}</span>
          <span>{ends[1]}</span>
        </div>
      )}
    </div>
  )
}
