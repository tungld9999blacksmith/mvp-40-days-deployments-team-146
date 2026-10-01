# EV Care AI Agent – Design Guidelines

## Aesthetic Stance
Premium Dark. Futuristic, trustworthy, technology-focused. Inspired by high-end EV brand dashboards (Rivian, Lucid, Tesla). Clean, minimal, high contrast.

## Colors
| Token | Value | Usage |
|---|---|---|
| `--color-background` | `#0B0F0E` | Page background |
| `--color-surface` | `#121817` | Sidebar, topbar, panels |
| `--color-card` | `#171D1C` | Cards, tables, forms |
| `--color-emerald` | `#10B981` | Primary CTA, active state, success |
| `--color-foreground` | `#F5F7F6` | Primary text |
| `--color-muted` | `#8D9995` | Secondary text, labels, icons |
| `--color-border` | `#1F2A28` | All hairline borders |
| `--color-warning` | `#F59E0B` | Due soon, pending approval |
| `--color-error` | `#EF4444` | Overdue, rejected, error states |

## Typography
- **Font**: Inter (Google Fonts, all weights 300–800)
- **Data/Code**: JetBrains Mono (biển số, km values, prices, timestamps)
- **Display**: 800 weight for stat values, 700 for page titles
- **Body**: 400–500 weight, 14px base size

## Status Badges
All status badges use `font-mono uppercase tracking-wide text-xs`:
- `NORMAL` / `COMPLETED` → `text-emerald bg-emerald/10`
- `DUE SOON` / `PENDING APPROVAL` → `text-warning bg-warning/10`
- `OVERDUE` / `REJECTED` / `ERROR` → `text-error bg-error/10`
- `CANCELLED` / neutral → `text-muted bg-card`

## Layout
- Sidebar: 240px fixed, `bg-surface`, `border-r border-border`
- Topbar: 64px fixed, `bg-surface`, `border-b border-border`
- Content: fluid, scrollable, `bg-background`, padding `p-6 xl:p-8`
- Cards: `bg-card`, `rounded-2xl`, `border border-border`

## Component Patterns
- **Buttons primary**: `bg-emerald text-background font-semibold rounded-xl`
- **Buttons secondary**: `bg-card border border-border text-muted hover:text-foreground`
- **Buttons danger**: `text-error border border-error/20 hover:bg-error/10`
- **Inputs**: `bg-card border border-border rounded-xl text-foreground focus:ring-1 focus:ring-emerald/40`
- **Nav active**: `bg-emerald/10 text-emerald rounded-xl`
- **Nav inactive**: `text-muted hover:text-foreground hover:bg-card`

## Navigation
Two roles, same Premium Dark shell:
- **Owner**: Tổng quan → Xe của tôi → Lịch sử → Đặt lịch → AI Trợ lý → Thông báo
- **Technician**: Dashboard → Báo giá → Thông báo → Khách hàng

## Prototype Flow
Login → Owner Dashboard → Vehicle Detail / AI Assistant / Booking
AI Assistant → Maintenance Estimate → Booking → Booking Success
Login (Technician) → Tech Dashboard → Pending Quotes → Quote Review → Approve
