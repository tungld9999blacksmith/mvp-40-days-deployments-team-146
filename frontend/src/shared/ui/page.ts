/**
 * Page container of the owner app: padding plus one of three widths (DESIGN.md, 2026-10-12).
 * - `full`: pages that fill the content area (Dashboard grid, context rail at xl);
 * - `reading`: single-column lists, details and forms, left-aligned;
 * - `ticket`: one centred card (booking ticket, follow-up).
 * Loading and error states use the same width as the page they belong to.
 */
export type PageWidth = 'full' | 'reading' | 'ticket'

const WIDTH: Record<PageWidth, string> = {
  full: '',
  reading: ' max-w-3xl',
  ticket: ' max-w-xl mx-auto',
}

export const page = (width: PageWidth = 'full') => `p-4 sm:p-6 xl:p-8${WIDTH[width]}`
