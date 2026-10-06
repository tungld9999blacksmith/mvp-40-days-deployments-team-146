import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { cn } from './cn'

export interface CarouselSlide {
  id: string
  /** Accessible name of the slide, e.g. "Hạn bảo dưỡng". */
  label: string
  content: ReactNode
}

/** Next index with wrap-around (exported for tests). */
export function wrapIndex(index: number, count: number): number {
  if (count <= 0) return 0
  return ((index % count) + count) % count
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/**
 * Cockpit banner: slides stack in one ink panel and crossfade. Autoplays every `interval` ms,
 * pauses on hover/focus or with the pause button, never autoplays under prefers-reduced-motion,
 * and supports swipe. Controls sit inside the panel; a single slide renders without them.
 */
export default function Carousel({ slides, label, interval = 6000, className }: {
  slides: CarouselSlide[]
  label: string
  interval?: number
  className?: string
}) {
  const count = slides.length
  const [index, setIndex] = useState(0)
  const [userPaused, setUserPaused] = useState(prefersReducedMotion)
  const [hovering, setHovering] = useState(false)
  const touchX = useRef<number | null>(null)
  const active = wrapIndex(index, count)
  const paused = userPaused || hovering || count < 2

  const go = useCallback((next: number) => setIndex(wrapIndex(next, count)), [count])

  useEffect(() => {
    if (paused) return
    const timer = window.setTimeout(() => go(active + 1), interval)
    return () => window.clearTimeout(timer)
  }, [active, paused, interval, go])

  if (count === 0) return null

  return (
    <section
      aria-roledescription="carousel"
      aria-label={label}
      className={cn('relative overflow-hidden rounded-2xl border border-banner-border bg-banner text-banner-foreground', className)}
      style={{ '--carousel-interval': `${interval}ms` } as CSSProperties}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onFocus={() => setHovering(true)}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHovering(false)
      }}
      onTouchStart={event => {
        touchX.current = event.touches[0]?.clientX ?? null
      }}
      onTouchEnd={event => {
        const start = touchX.current
        touchX.current = null
        const end = event.changedTouches[0]?.clientX
        if (start === null || end === undefined || Math.abs(end - start) < 40) return
        go(active + (end < start ? 1 : -1))
      }}
    >
      {/* All slides share one grid cell, so the panel takes the height of the tallest one. */}
      <div className="grid">
        {slides.map((slide, i) => {
          const isActive = i === active
          return (
            <div
              key={slide.id}
              role="group"
              aria-roledescription="slide"
              aria-label={`${slide.label} (${i + 1}/${count})`}
              aria-hidden={!isActive}
              inert={!isActive}
              className={cn(
                // Centred: shorter slides split the spare height above and below instead of leaving it at the bottom.
                '[grid-area:1/1] flex flex-col justify-center p-6 sm:p-8 transition-[opacity,visibility] duration-700 ease-out motion-reduce:transition-none',
                count > 1 && 'pb-20 sm:pb-20',
                isActive ? 'opacity-100 visible' : 'opacity-0 invisible',
              )}
            >
              {slide.content}
            </div>
          )
        })}
      </div>

      {count > 1 && (
        <div className="absolute inset-x-6 sm:inset-x-8 bottom-5 flex items-center justify-between gap-3">
          <div className="flex items-center -mx-[3px]">
            {slides.map((slide, i) => (
              // The visible bar stays 6px; the padded button gives a 40px-tall tap target.
              <button
                key={slide.id}
                type="button"
                onClick={() => go(i)}
                aria-label={`Xem: ${slide.label}`}
                aria-current={i === active}
                className="group py-[17px] px-[3px]"
              >
                <span
                  className={cn(
                    'relative block h-1.5 overflow-hidden rounded-full bg-banner-foreground/25 transition-[width] duration-300',
                    i === active ? 'w-12' : 'w-6 group-hover:bg-banner-foreground/40',
                  )}
                >
                  {i === active && (
                    <span
                      key={`${active}-${paused}`}
                      aria-hidden
                      className={cn('absolute inset-y-0 left-0 rounded-full bg-banner-foreground', paused ? 'w-full opacity-50' : 'animate-carousel-fill')}
                    />
                  )}
                </span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <CarouselButton label={userPaused ? 'Tiếp tục tự chuyển' : 'Dừng tự chuyển'} onClick={() => setUserPaused(p => !p)}>
              {userPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            </CarouselButton>
            <CarouselButton label="Slide trước" onClick={() => go(active - 1)}>
              <ChevronLeft className="w-4 h-4" />
            </CarouselButton>
            <CarouselButton label="Slide sau" onClick={() => go(active + 1)}>
              <ChevronRight className="w-4 h-4" />
            </CarouselButton>
          </div>
        </div>
      )}
    </section>
  )
}

function CarouselButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="w-9 h-9 rounded-full border border-banner-foreground/30 bg-banner-foreground/10 text-banner-foreground hover:bg-banner-foreground/20 flex items-center justify-center transition-colors"
    >
      {children}
    </button>
  )
}
