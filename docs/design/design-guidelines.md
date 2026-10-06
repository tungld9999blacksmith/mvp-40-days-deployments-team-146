# EV Care AI Agent – Design Guidelines

> **Superseded (2026-10-04):** the design source of truth is now [DESIGN.md](../../DESIGN.md) at the repo root (light showroom theme, white sidebar, EV CARE logo, ink cockpit banner on Home, no gradients or glows). This file describes the previous dark emerald → cyan look and is kept for history only.

## Aesthetic Stance
Modern Premium. Futuristic, trustworthy, technology-focused. Inspired by high-end EV brand dashboards (Rivian, Lucid, Tesla). Clean and minimal, with soft depth: hairline borders, soft shadows, a restrained emerald → cyan brand gradient and very soft background glows. Two themes (dark by default, light) share one set of tokens.

## Colors
Tokens live in `frontend/src/styles/index.css` (`@theme`). The light theme overrides the same tokens under `:root[data-theme='light']`.

| Token | Dark | Light | Usage |
|---|---|---|---|
| `--color-background` | `#090C0B` | `#F4F6F5` | Page background |
| `--color-surface` | `#0F1413` | `#FFFFFF` | Sidebar, topbar, dialogs (translucent + blur in the shell) |
| `--color-card` | `#131918` | `#FFFFFF` | Cards, tables, forms |
| `--color-card-hover` | `#1A2120` | `#F0F4F2` | Hover fill |
| `--color-emerald` | `#10B981` | `#059669` | Primary accent, active state, success |
| `--color-emerald-bright` | `#34D399` | `#047857` | Hover of emerald text/links |
| `--color-accent` | `#22D3EE` | `#0891B2` | Second stop of the brand gradient only |
| `--color-on-brand` | `#04130D` | `#FFFFFF` | Text/icons on the brand gradient |
| `--color-foreground` | `#F4F7F6` | `#0E1614` | Primary text |
| `--color-muted` | `#8A9692` | `#5A6662` | Secondary text, labels, icons |
| `--color-border` | `#1E2725` | `#E1E7E4` | All hairline borders |
| `--color-warning` | `#F59E0B` | `#B45309` | Due soon, pending approval |
| `--color-error` | `#EF4444` | `#DC2626` | Overdue, rejected, error states |

Never hard-code hex values in components: use the tokens (or `var(--color-*)` in inline styles) so both themes work.

## Depth & gradients
Custom utilities (defined with `@utility` in `index.css`, values switch with the theme):
- `elevation-sm`: every card / panel / input. `elevation-md`: dialogs, drawers, toasts, hover of clickable cards.
- `glow-emerald`: coloured shadow under the primary action and the brand mark.
- `bg-brand-gradient`: primary buttons, the brand mark, the avatar fallback. One primary action per view.
- `text-brand-gradient`: at most one highlighted phrase per screen (greeting name, login headline).
- `bg-app-backdrop`: two very soft glows behind the app shell and the login form.

## Typography
- **Font**: Be Vietnam Pro (Google Fonts, 300–800): designed for Vietnamese diacritics.
- **Data/Code**: JetBrains Mono (biển số, VIN, km values, prices, timestamps)
- **Display**: 700 + `tracking-tight` for page titles (`text-2xl`/`text-3xl`), 800 for stat values
- **Body**: 400–500 weight, 14px base size
- **Card titles** (`CardHeader`): sentence case, `text-[13px] font-semibold text-muted`

## Status Badges
Pill, sentence case, sans font, leading dot (or icon), `text-xs font-medium ring-1 ring-inset`:
- Normal / completed → `text-emerald bg-emerald/10 ring-emerald/20`
- Due soon / pending approval → `text-warning bg-warning/10 ring-warning/20`
- Overdue / rejected / error → `text-error bg-error/10 ring-error/20`
- Cancelled / neutral → `text-muted bg-foreground/5 ring-foreground/10`

## Layout
- Sidebar: 240px fixed, `bg-surface/70 backdrop-blur-xl`, `border-r border-border`, "Menu" caption above the nav
- Topbar: 64px, `bg-surface/60 backdrop-blur-xl`, `border-b border-border`; left: current section title; right: theme toggle, notifications, divider, user pill
- Content: fluid, scrollable, `bg-background` + `bg-app-backdrop`, padding `p-4 sm:p-6 xl:p-8`; pages fade in (`animate-fade-in`)
- Cards: `bg-card`, `rounded-2xl`, `border border-border`, `elevation-sm`; dialogs `rounded-3xl elevation-md`

## Component Patterns
- **Buttons primary**: `bg-brand-gradient text-on-brand font-semibold glow-emerald rounded-xl hover:brightness-110 active:scale-[0.98]`
- **Buttons secondary**: `bg-card border border-border text-foreground/80 elevation-sm hover:text-foreground hover:bg-card-hover`
- **Buttons danger**: `text-error border border-error/25 hover:bg-error/10`
- **Icon buttons (topbar)**: round, `w-9 h-9 rounded-full bg-card/60 border border-border` (`shared/ui/iconButton.ts`)
- **Inputs**: `bg-card border border-border rounded-xl elevation-sm focus:border-emerald/60 focus:ring-4 focus:ring-emerald/15`
- **Clickable cards**: `hover:-translate-y-0.5 hover:elevation-md hover:border-emerald/30 transition-all`
- **Nav active**: `bg-emerald/10 text-foreground ring-1 ring-emerald/15`, emerald icon, 4px emerald bar on the left edge
- **Nav inactive**: `text-muted hover:text-foreground hover:bg-foreground/5`
- **Overlays**: `bg-black/50 backdrop-blur-sm`
- **Motion**: 200 ms transitions, `animate-pop-in` for dialogs/toasts; everything is disabled under `prefers-reduced-motion`

## Theme
- Toggle (sun / moon) in the topbar, left of the notifications bell (`shared/ui/ThemeToggle.tsx`).
- Choice is stored per browser (`localStorage` key `evcare.theme`) and applied before first paint by the inline script in `index.html`.

## Navigation
Two roles, same shell:
- **Owner**: Tổng quan → Xe của tôi → Lịch sử → Đặt lịch → AI Trợ lý → Thông báo
- **Technician**: Dashboard → Lịch hẹn → Thông báo → Khách hàng

## Prototype Flow
Login → Owner Dashboard → Vehicle Detail / AI Assistant / Booking
AI Assistant → Maintenance Estimate → Booking → Booking Success
Login (Technician) → Tech Dashboard → Workshop Board → Booking detail → Accept
