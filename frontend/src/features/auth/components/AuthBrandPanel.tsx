import { Shield } from 'lucide-react'
import Logo from '@/shared/ui/Logo'

/** Left half of the login screens: brand, headline, feature chips. Hidden below lg (see AuthMobileBrand). Ink like the Home banner. */
export default function AuthBrandPanel({
  headline,
  highlight,
  subtitle,
  chips,
  badge,
}: {
  headline: string
  highlight: string
  subtitle: string
  chips: string[]
  badge?: string
}) {
  return (
    <div className="hidden lg:flex lg:w-[55%] relative flex-col justify-between p-12 overflow-hidden bg-banner text-banner-foreground border-r border-banner-border">
      <div className="relative flex items-center gap-3">
        <Logo className="h-12 text-banner-foreground" />
        {badge && (
          <span className="ml-1 px-2.5 py-1 rounded-full text-xs font-semibold text-banner-accent bg-banner-accent/15 ring-1 ring-inset ring-banner-accent/30">{badge}</span>
        )}
      </div>

      <div className="relative max-w-lg">
        <h1 className="text-5xl font-extrabold tracking-tight text-banner-foreground leading-[1.1] mb-5 text-balance">
          {headline}
          <br />
          <span className="text-banner-accent">{highlight}</span>
        </h1>
        <p className="text-banner-muted text-lg leading-relaxed">{subtitle}</p>
        <div className="flex flex-wrap gap-2 mt-8">
          {chips.map(chip => (
            <span key={chip} className="px-3.5 py-1.5 rounded-full text-xs font-medium text-banner-foreground/90 bg-white/5 border border-banner-border">
              {chip}
            </span>
          ))}
        </div>
      </div>

      <div className="relative flex items-center gap-2 text-banner-muted text-sm">
        <Shield className="w-4 h-4 text-banner-accent" />
        <span>EV Care – Smart EV After-sales Platform</span>
      </div>
    </div>
  )
}

/** Below lg the brand panel is hidden: logo plus the same headline and promise, so phones still see what the product does. */
export function AuthMobileBrand({ headline, highlight, subtitle, badge }: { headline: string; highlight: string; subtitle: string; badge?: string }) {
  return (
    <div className="lg:hidden w-full max-w-sm sm:max-w-md mb-8">
      <div className="flex items-center gap-2.5">
        <Logo className="h-9 text-foreground" />
        {badge && <span className="text-xs font-semibold text-emerald">{badge}</span>}
      </div>
      <p className="mt-6 text-2xl font-extrabold tracking-tight text-foreground leading-tight text-balance">
        {headline} <span className="text-emerald">{highlight}</span>
      </p>
      <p className="mt-2 text-sm text-muted leading-relaxed">{subtitle}</p>
    </div>
  )
}
