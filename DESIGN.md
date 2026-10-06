---
# gstack: design-md-format=spec
name: EV Care
description: Clean showroom-light surfaces with the black-and-green EV CARE logo, solid green actions, and one ink cockpit banner on Home with instrument-style readouts.
colors:
  background: "#F5F6F7"
  surface: "#FFFFFF"
  card-hover: "#F2F4F5"
  border: "#E3E6E9"
  text: "#111820"
  text-muted: "#5B6670"
  primary: "#007A52"
  primary-hover: "#00643F"
  on-primary: "#FFFFFF"
  primary-tint: "#E6F4EE"
  logo-bolt: "#00A86B"
  success: "#007A52"
  warning: "#B45309"
  error: "#DC2626"
  sidebar: "#FFFFFF"
  sidebar-active: "#E6F4EE"
  banner: "#111820"
  banner-text: "#EEF2F5"
  banner-muted: "#94A0AC"
  banner-border: "#2A3642"
  banner-accent: "#19C37D"
  banner-on-accent: "#0A0E13"
  banner-alert: "#FBBF24"
  plate: "#FFFFFF"
  plate-ink: "#111820"
  dark-background: "#0B0F14"
  dark-surface: "#0F151B"
  dark-card: "#131A21"
  dark-card-hover: "#19222B"
  dark-border: "#222C36"
  dark-text: "#EEF2F5"
  dark-text-muted: "#8B97A4"
  dark-primary: "#19C37D"
  dark-on-primary: "#0B0F14"
  dark-accent-text: "#3AD493"
  dark-warning: "#F59E0B"
  dark-error: "#F87171"
  dark-sidebar: "#0F151B"
  dark-sidebar-active: "#10291F"
  dark-banner: "#10161D"
typography:
  heading:
    fontFamily: Be Vietnam Pro
    fontWeight: 800
    fontSize: 1.875rem
    lineHeight: 1.2
    letterSpacing: -0.025em
  body:
    fontFamily: Be Vietnam Pro
    fontWeight: 400
    fontSize: 0.875rem
    lineHeight: 1.55
  label:
    fontFamily: Be Vietnam Pro
    fontWeight: 600
    fontSize: 0.8125rem
  instrument-label:
    fontFamily: JetBrains Mono
    fontWeight: 500
    fontSize: 0.71875rem
    letterSpacing: 0.06em
  mono:
    fontFamily: JetBrains Mono
    fontWeight: 500
    fontSize: 0.8125rem
    fontFeature: tnum
  figure:
    fontFamily: Barlow Condensed
    fontWeight: 700
    fontSize: 2.15rem
    lineHeight: 1
rounded:
  sm: 6px
  md: 10px
  lg: 14px
  xl: 20px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
  input:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
  card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    rounded: "{rounded.lg}"
  dialog:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.xl}"
  sidebar:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.text}"
  nav-link-active:
    backgroundColor: "{colors.sidebar-active}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
  banner:
    backgroundColor: "{colors.banner}"
    textColor: "{colors.banner-text}"
    borderColor: "{colors.banner-border}"
    rounded: "{rounded.lg}"
  banner-button:
    backgroundColor: "{colors.banner-accent}"
    textColor: "{colors.banner-on-accent}"
    rounded: "{rounded.md}"
  plate:
    backgroundColor: "{colors.plate}"
    textColor: "{colors.plate-ink}"
    borderColor: "{colors.plate-ink}"
    rounded: "{rounded.sm}"
  status-badge:
    rounded: "{rounded.full}"
---

# EV Care

## Overview

**Creative North Star:** "Showroom sáng" with a cockpit banner. Working surfaces are white and light grey, clean like a car showroom, so the black-and-green EV CARE logo and the solid green actions carry the brand. Home opens with one ink banner styled like an instrument cluster: mono uppercase labels and large condensed readouts.

**Product context:** Vietnamese-language web app (React 19 + Tailwind v4) for private VinFast owners: maintenance due status, AI assistant, cost estimate, booking. The Workshop Portal (technicians) shares the same shell. The real competitor is the official VinFast app.

**Mode per surface:** Owner app and Workshop Portal are Operate surfaces. Login is the one Persuade surface.

**Layout is fixed.** This system restyles the existing structure (240px sidebar, 64px topbar, card grid, booking flows). It does not move screens, menus or flows. Layout changes need their own decision.

**Approved reference:** `/design-shotgun` 2026-10-04 (`~/.gstack/projects/<slug>/designs/dashboard-refresh-20261004/`). Shell from variant A "Showroom sáng"; Home banner from variant B "Buồng lái đêm". Variant C was applied first, then replaced at the user's request.

**Key characteristics:**
- The real EV CARE logo in the sidebar, login, splash, onboarding and favicon.
- White sidebar, light grey ground, white cards with soft shadows.
- Solid green buttons with white text. No gradients, no coloured glows.
- One family for text (Be Vietnam Pro); mono and condensed figures only where they mean data.
- Licence plates drawn as real plates.
- Home banner: ink panel, crossfading slides, real data only.

## Colors

**Strategy:** Restrained. Ink and one green (from the logo family) on neutrals. Warning and error are the only other hues. The banner is the single dark, high-contrast object on light pages.

**Light or dark:** Light is the default (owners open the app on phones in daylight; Demo Day projectors favour light). Dark is a full alternative under `:root[data-theme='dark']`, stored per browser in `localStorage` key `evcare.theme.v2`.

**Rules:**
- `--color-emerald` / `--color-brand` `#007A52` is the action green for text, icons and fills; white text on it is 5.38:1. In dark both become bright greens (`#3AD493` text, `#19C37D` fill) with near-black text on fills.
- `--color-logo-bolt` (`#00A86B`, dark `#19C37D`) is only for the bolt inside the logo. Never use it for text on light surfaces (3.08:1).
- Banner tokens (`banner-*`) are ink in both themes. On the banner, muted text is `#94A0AC` (6.71:1), the accent button is `#19C37D` with `#0A0E13` text (8.43:1), and readouts that caused the due alert turn amber (`amber-400`).
- `bg-brand-gradient` still exists for old class lists but paints solid `--color-brand`; `text-brand-gradient` paints solid `--color-emerald`; `glow-emerald` and `bg-app-backdrop` are no-ops. New code uses `bg-brand`, `text-emerald` directly.
- Plates stay white with ink in both themes. Dark error is `#F87171` for legible small text.

## Typography

All families load from one Google Fonts request in `frontend/src/styles/index.css`; all have Vietnamese subsets (verified 2026-10-04).

- **Be Vietnam Pro** (300–800): all text. Page greeting 800 at 24–30px with -0.025em tracking; banner titles 800; body 14px; labels 13px semibold; sentence case.
- **JetBrains Mono** (`font-mono`): km values, prices, timestamps, VIN, booking codes, and the uppercase instrument labels in the banner (11–11.5px, 0.06em tracking).
- **Barlow Condensed** (`font-plate`): licence plates (`PlateTile`), banner readouts, and the due figure on the maintenance card.

## Layout

Unchanged from the existing app: 240px sidebar (drawer below `lg`), 64px topbar, content padding `p-4 sm:p-6 xl:p-8`, Dashboard grid (`xl:grid-cols-3`); on xl the quick actions stack under the AI card in the right column. On `sm`–`lg` the topbar shows the logo because the sidebar is hidden. The Home banner sits between the greeting and the upcoming-booking highlight, full content width; all slides share one grid cell, so its height is the tallest slide and the page never jumps; slide content is centred vertically in that cell.

## Elevation & Depth

- `elevation-sm`: `0 1px 2px` ink 4% + `0 8px 24px -16px` ink 18% for cards and inputs.
- `elevation-md`: dialogs, drawers, toasts, card hover.
- The banner has no shadow; its ink fill and hairline border give it weight.
- No coloured halos, no radial page glows, no decorative blur blobs.

## Shapes

Tailwind radius tokens are overridden: `rounded-xl` = 10px (buttons, inputs, nav items, chips), `rounded-2xl` = 14px (cards, banner, readout grid), `rounded-3xl` = 20px (dialogs, login card). Status badges and avatars stay `rounded-full`. Plates use 6px.

## Components

- **Logo** (`shared/ui/Logo.tsx`): inline SVG from `public/brand/ev-care-logo.svg`. Ink parts use `currentColor` (`text-foreground` / `text-sidebar-foreground` on light, `text-banner-foreground` on ink); the bolt uses `--color-logo-bolt`. `variant="mark"` for tight spots. Favicon: white mark on an ink rounded square.
- **Sidebar** (`layouts/AppLayout.tsx`): `bg-sidebar` (white / near-black), inactive items `text-sidebar-muted` with `hover:bg-sidebar-hover`, active item `bg-sidebar-active` with a green icon, count badges `bg-brand text-on-brand`.
- **Carousel** (`shared/ui/Carousel.tsx`): one ink panel; slides stack and crossfade over 700ms. Autoplay 6s with a filling dot, pauses on hover, focus and the pause button. No autoplay under `prefers-reduced-motion`; swipe on touch; inactive slides are `inert`. Controls (dots, pause, prev/next) sit inside the panel, bottom edge. A single slide renders without controls.
- **HomeCarousel** (`features/dashboard/components/HomeCarousel.tsx`): slides only from real data or real features (`homeSlides.ts`): maintenance (known milestone; readouts for km and days left, from `sm` up), booking (only when nothing is upcoming), assistant (always, with suggested questions from `sm` up). No promotional slide until there is a real source of offers.
- **Login brand panel** (`AuthBrandPanel.tsx`): banner tokens, white logo, green highlight phrase.
- **PlateTile** (`shared/ui/PlateTile.tsx`): white plate, ink border, Barlow Condensed.
- **Buttons**: primary `bg-brand` + `text-on-brand`; secondary card + border; danger error text and border.
- **Quick actions**: green-tint icon tile (`bg-emerald-dim text-emerald`) beside the label from `sm` up.

## Do's and Don'ts

- Do use `bg-brand` + `text-on-brand` for primary fills and `text-emerald` for green text.
- Do render the real logo through `<Logo />` and plates through `<PlateTile />`.
- Do keep the banner the only ink block on a page, with real data and a working action on every slide.
- Do check both themes and 390px width before merging UI changes.
- Don't use gradients, glows, blur blobs or gradient text.
- Don't use mono uppercase labels outside the banner; elsewhere labels are sentence case.
- Don't use the logo green `#00A86B` as text on light surfaces.
- Don't change layout or navigation as part of a visual change.

## Motion

- **Approach:** quiet and functional.
- **Durations:** 150–200ms for hover and colour, 300ms for the carousel dot width, 700ms ease-out crossfade between banner slides, 6s autoplay interval.
- **The one authored moment:** the Home banner crossfade with the filling progress dot.
- Everything respects `prefers-reduced-motion` (no autoplay, no transitions).

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-04 | DESIGN.md created; supersedes docs/design/design-guidelines.md | User asked for a prettier, more modern UI with a moving banner and the new EV CARE logo, keeping the current structure. |
| 2026-10-04 | Variant C "Xanh thương hiệu" applied first, then replaced by variant A "Showroom sáng" with the variant B cockpit banner | User's choice after seeing C in the app. |
| 2026-10-04 | Light becomes the default theme; storage key moves to `evcare.theme.v2` | Daylight phone use. The old hook wrote the default into storage on every visit, so the key change is what lets existing browsers see the new default. |
| 2026-10-04 | Retired the emerald → cyan gradient, glows and backdrop halos; utilities kept as solid/no-op aliases | Generic AI-dashboard look; aliases avoid touching every class list at once. |
| 2026-10-04 | Action green `#007A52` (white text); logo green `#00A86B` reserved for the logo bolt | `#00A86B` is only 3.08:1 as text and 3.08:1 under white text. |
| 2026-10-04 | Home banner shows only real data; no promo slide | No source of offers exists yet; a fabricated promotion would mislead owners. |
| 2026-10-04 | Home (xl): quick actions move under the AI card; the vehicle photo fills its card | Right column sat empty below the AI card and the vehicle card had a ~200px gap. Order below xl unchanged. (design review FINDING-011) |
| 2026-10-04 | Banner slides centre vertically; below `sm` the readouts and the assistant questions are hidden | On phones they repeated the headline and the AI card, and made the banner 507px tall with 180px empty under the short slide. (design review FINDING-012) |
| 2026-10-04 | Workshop › Lịch hẹn: status count cards and status chips merge into one row of count-filter buttons (multi-select) | The six cards and six chips repeated each other and took three rows on phones. (design review FINDING-013) |
| 2026-10-04 | Owner nav: "Lịch hẹn" → "Lịch hẹn của tôi" (ticket icon), "Đặt lịch" → "Đặt lịch bảo dưỡng" | Two adjacent calendar items read alike; labels now match the page titles. Order and routes unchanged. (design review FINDING-016) |
| 2026-10-04 | Workshop › Sức chứa cells lead with seats left (16px mono); booked and locked lines only when non-zero; full slots read "Hết chỗ" | 56 identical three-line 11px cells hid the few slots that mattered. (design review FINDING-018) |
