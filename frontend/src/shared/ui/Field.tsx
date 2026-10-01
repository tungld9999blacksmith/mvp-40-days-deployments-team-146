import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { AlertCircle } from 'lucide-react'
import { cn } from './cn'

const controlBase =
  'w-full bg-card border rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted ' +
  'focus:outline-none focus:ring-1 focus:ring-emerald/40 transition-colors disabled:opacity-60 disabled:cursor-not-allowed'

function controlClass(error: string | undefined, className?: string) {
  return cn(controlBase, error ? 'border-error' : 'border-border', className)
}

interface FieldProps {
  label: string
  error?: string
  helper?: ReactNode
  required?: boolean
  optional?: boolean
  /** Rendered after the label, e.g. a character counter. */
  aside?: ReactNode
  children: (ids: { inputId: string; describedBy: string | undefined; invalid: boolean }) => ReactNode
}

/** Label + control + helper + inline error, wired with aria attributes. */
export function Field({ label, error, helper, required, optional, aside, children }: FieldProps) {
  const inputId = useId()
  const helperId = `${inputId}-helper`
  const errorId = `${inputId}-error`
  const describedBy = [error ? errorId : null, helper ? helperId : null].filter(Boolean).join(' ') || undefined

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <label htmlFor={inputId} className="block text-sm font-medium text-foreground">
          {label}
          {required && <span className="text-error ml-0.5" aria-hidden>*</span>}
          {optional && <span className="text-muted font-normal ml-1.5 text-xs">(tuỳ chọn)</span>}
        </label>
        {aside}
      </div>
      {children({ inputId, describedBy, invalid: Boolean(error) })}
      {helper && !error && (
        <p id={helperId} className="text-xs text-muted mt-1.5">
          {helper}
        </p>
      )}
      {error && (
        <p id={errorId} className="flex items-start gap-1.5 text-xs text-error mt-1.5">
          <AlertCircle className="w-3.5 h-3.5 mt-px flex-shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  )
}

type BaseProps = { label: string; error?: string; helper?: ReactNode; optional?: boolean; aside?: ReactNode }

export const TextInput = forwardRef<HTMLInputElement, BaseProps & InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ label, error, helper, optional, aside, className, required, ...rest }, ref) {
    return (
      <Field label={label} error={error} helper={helper} required={required} optional={optional} aside={aside}>
        {({ inputId, describedBy, invalid }) => (
          <input
            ref={ref}
            id={inputId}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            aria-required={required || undefined}
            className={controlClass(error, className)}
            {...rest}
          />
        )}
      </Field>
    )
  },
)

export const TextArea = forwardRef<HTMLTextAreaElement, BaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ label, error, helper, optional, aside, className, required, ...rest }, ref) {
    return (
      <Field label={label} error={error} helper={helper} required={required} optional={optional} aside={aside}>
        {({ inputId, describedBy, invalid }) => (
          <textarea
            ref={ref}
            id={inputId}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            aria-required={required || undefined}
            className={controlClass(error, cn('resize-none', className))}
            {...rest}
          />
        )}
      </Field>
    )
  },
)

export const SelectInput = forwardRef<
  HTMLSelectElement,
  BaseProps & SelectHTMLAttributes<HTMLSelectElement> & { placeholder?: string }
>(function SelectInput({ label, error, helper, optional, aside, className, required, placeholder, children, ...rest }, ref) {
  return (
    <Field label={label} error={error} helper={helper} required={required} optional={optional} aside={aside}>
      {({ inputId, describedBy, invalid }) => (
        <select
          ref={ref}
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          aria-required={required || undefined}
          className={controlClass(error, cn('appearance-none', className))}
          {...rest}
        >
          {placeholder !== undefined && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {children}
        </select>
      )}
    </Field>
  )
})
