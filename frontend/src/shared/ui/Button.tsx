import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from './cn'
import Spinner from './Spinner'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const variants: Record<Variant, string> = {
  primary: 'bg-brand-gradient text-on-brand font-semibold glow-emerald hover:brightness-110',
  secondary: 'bg-card border border-border text-foreground/80 elevation-sm hover:text-foreground hover:bg-card-hover hover:border-foreground/15',
  danger: 'text-error border border-error/25 hover:bg-error/10',
  ghost: 'text-muted hover:text-foreground hover:bg-foreground/5',
}

const sizes: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-5 py-3 text-sm',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  loadingText?: string
  fullWidth?: boolean
  icon?: ReactNode
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, loadingText, fullWidth, icon, className, children, disabled, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 active:scale-[0.98]',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald/25',
        'disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 disabled:hover:brightness-100',
        variants[variant],
        sizes[size],
        fullWidth && 'w-full',
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {loading && loadingText ? loadingText : children}
    </button>
  )
})

export default Button
