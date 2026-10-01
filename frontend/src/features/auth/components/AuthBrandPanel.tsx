import { Zap, Shield } from 'lucide-react'

/** Left half of the login screens: brand, headline, feature chips. Hidden on mobile. */
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
    <div className="hidden lg:flex lg:w-[55%] relative flex-col justify-between p-12 overflow-hidden bg-background border-r border-border">
      {/* The only allowed gradient: a very soft emerald glow (design style §5.2). */}
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_30%_50%,var(--color-emerald)_0%,transparent_70%)] opacity-[0.06]"
      />

      <div className="relative flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-emerald flex items-center justify-center">
          <Zap className="w-5 h-5 text-background" strokeWidth={2.5} />
        </div>
        <span className="text-foreground font-bold text-2xl tracking-tight">EV Care</span>
        {badge && (
          <span className="ml-1 px-2.5 py-1 rounded-full text-xs font-semibold text-emerald bg-emerald/10">{badge}</span>
        )}
      </div>

      <div className="relative max-w-md">
        <h1 className="text-4xl font-bold text-foreground leading-tight mb-4">
          {headline}
          <br />
          <span className="text-emerald">{highlight}</span>
        </h1>
        <p className="text-muted text-lg leading-relaxed">{subtitle}</p>
        <div className="flex flex-wrap gap-2 mt-8">
          {chips.map(chip => (
            <span key={chip} className="px-3 py-1 rounded-full text-xs font-medium text-emerald bg-emerald/10 border border-emerald/20">
              {chip}
            </span>
          ))}
        </div>
      </div>

      <div className="relative flex items-center gap-2 text-muted text-sm">
        <Shield className="w-4 h-4 text-emerald" />
        <span>EV Care – Smart EV After-sales Platform</span>
      </div>
    </div>
  )
}
