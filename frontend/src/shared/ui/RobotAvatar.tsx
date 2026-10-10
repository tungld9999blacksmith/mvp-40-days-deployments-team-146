import { cn } from './cn'

export type RobotMood = 'idle' | 'thinking' | 'happy' | 'wave'

// Mascot colours are fixed like PlateTile: the white head reads on both themes.
const INK = '#111820'
const EYE = '#19C37D'
const EAR = '#007A52'
const CHEEK = '#FF9EAE'
const THINKING_LIGHT = '#FBBF24'

function Face({ mood }: { mood: RobotMood }) {
  if (mood === 'thinking') {
    return (
      <>
        <ellipse cx="27" cy="30.5" rx="3.2" ry="4" fill={EYE} />
        <ellipse cx="40" cy="30.5" rx="3.2" ry="4" fill={EYE} />
        <circle cx="28" cy="29.2" r="1.1" fill="#FFFFFF" />
        <circle cx="41" cy="29.2" r="1.1" fill="#FFFFFF" />
        <path d="M29 40 L35 40" stroke={EYE} strokeWidth="2.4" strokeLinecap="round" />
      </>
    )
  }
  if (mood === 'happy' || mood === 'wave') {
    return (
      <>
        <path d="M21.5 33.5 Q25 28.5 28.5 33.5" stroke={EYE} strokeWidth="2.8" fill="none" strokeLinecap="round" />
        <path d="M35.5 33.5 Q39 28.5 42.5 33.5" stroke={EYE} strokeWidth="2.8" fill="none" strokeLinecap="round" />
        <path d="M28 38 Q32 44 36 38 Z" fill={EYE} />
      </>
    )
  }
  return (
    <>
      <ellipse cx="25" cy="32" rx="3.4" ry="4.4" fill={EYE} />
      <ellipse cx="39" cy="32" rx="3.4" ry="4.4" fill={EYE} />
      <circle cx="26.2" cy="30.3" r="1.2" fill="#FFFFFF" />
      <circle cx="40.2" cy="30.3" r="1.2" fill="#FFFFFF" />
      <path d="M28 39 Q32 42.5 36 39" stroke={EYE} strokeWidth="2.4" fill="none" strokeLinecap="round" />
    </>
  )
}

/** The assistant's robot mascot, drawn on a 64-unit grid. Decorative unless `label` is given. */
export function RobotMascot({ mood = 'idle', size = 32, label, className }: { mood?: RobotMood; size?: number; label?: string; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <line x1="32" y1="6" x2="32" y2="13" stroke={INK} strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="32" cy="5.5" r="3.6" fill={mood === 'thinking' ? THINKING_LIGHT : EYE} stroke={INK} strokeWidth="2.2" />
      <rect x="4.5" y="28" width="7" height="13" rx="3.5" fill={EAR} stroke={INK} strokeWidth="2.2" />
      {mood === 'wave' ? (
        <>
          <path d="M56 30 L60.5 20" stroke={INK} strokeWidth="2.6" strokeLinecap="round" />
          <circle cx="60.5" cy="18" r="3.2" fill={EAR} stroke={INK} strokeWidth="2" />
        </>
      ) : (
        <rect x="52.5" y="28" width="7" height="13" rx="3.5" fill={EAR} stroke={INK} strokeWidth="2.2" />
      )}
      <rect x="9" y="13" width="46" height="43" rx="17" fill="#FFFFFF" stroke={INK} strokeWidth="2.6" />
      <rect x="15" y="20.5" width="34" height="25" rx="11" fill={INK} />
      <Face mood={mood} />
      <ellipse cx="17.5" cy="50" rx="3.4" ry="2.2" fill={CHEEK} />
      <ellipse cx="46.5" cy="50" rx="3.4" ry="2.2" fill={CHEEK} />
    </svg>
  )
}

/** Round avatar: the mascot on a green-tint disc, optionally with an "online" dot. */
export default function RobotAvatar({ mood = 'idle', size = 36, online, className }: { mood?: RobotMood; size?: number; online?: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn('relative inline-flex items-center justify-center rounded-full bg-emerald-dim flex-shrink-0', className)}
      style={{ width: size, height: size }}
    >
      <RobotMascot mood={mood} size={Math.round(size * 0.8)} />
      {online && <span className="absolute right-0 bottom-0 w-3 h-3 rounded-full bg-brand border-2 border-surface" />}
    </span>
  )
}
