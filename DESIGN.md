---
# gstack: design-md-format=spec
name: EV Care
description: The car's second screen, with a co-pilot. Home opens on an ink instrument cluster (gauges, the car, tell-tale lamps, a voice bar to the assistant); other pages use titanium neutrals with a sidebar that follows light/dark mode, where the assistant speaks in thin ink copilot lines in its own cyan. Saira instrument type, solid green actions.
colors:
  background: "#EEF1F4"
  surface: "#FFFFFF"
  card-hover: "#F4F6F8"
  border: "#DCE1E6"
  text: "#0E151C"
  text-muted: "#56616C"
  primary: "#007A52"
  primary-hover: "#00643F"
  on-primary: "#FFFFFF"
  primary-tint: "#E3F3EC"
  logo-bolt: "#00A86B"
  success: "#007A52"
  warning: "#B45309"
  warning-tint: "#FCEFDF"
  error: "#DC2626"
  sidebar: "#FFFFFF"
  sidebar-text: "#56616C"
  sidebar-active: "#E3F3EC"
  sidebar-active-text: "#0E151C"
  sidebar-border: "#DCE1E6"
  banner: "#0B1218"
  banner-text: "#EEF2F5"
  banner-muted: "#94A0AC"
  banner-border: "#24313C"
  banner-raised: "#16212B"
  banner-accent: "#19C37D"
  banner-on-accent: "#0A0E13"
  banner-alert: "#FBBF24"
  banner-danger: "#F87171"
  lamp-off: "#2E3A44"
  assistant-signal: "#22C7DD"
  plate: "#FFFFFF"
  plate-ink: "#0E151C"
  dark-background: "#0A0F14"
  dark-surface: "#0F161D"
  dark-card: "#111921"
  dark-card-hover: "#17212B"
  dark-border: "#233039"
  dark-text: "#EEF2F5"
  dark-text-muted: "#8B97A4"
  dark-primary: "#19C37D"
  dark-on-primary: "#0B0F14"
  dark-accent-text: "#3AD493"
  dark-primary-tint: "#10291F"
  dark-warning: "#F59E0B"
  dark-warning-tint: "#2A1D0A"
  dark-error: "#F87171"
  dark-sidebar: "#070B0F"
  dark-sidebar-active: "#16212B"
  dark-banner: "#0F171F"
typography:
  heading:
    fontFamily: Saira
    fontWeight: 700
    fontStretch: 112%
    fontSize: 1.875rem
    lineHeight: 1.15
    letterSpacing: -0.01em
  body:
    fontFamily: Inter
    fontWeight: 400
    fontSize: 0.875rem
    lineHeight: 1.55
  label:
    fontFamily: Inter
    fontWeight: 600
    fontSize: 0.8125rem
  instrument-label:
    fontFamily: Inter
    fontWeight: 500
    fontSize: 0.71875rem
    letterSpacing: 0.06em
  mono:
    fontFamily: Inter
    fontWeight: 500
    fontSize: 0.8125rem
    fontFeature: tnum
  figure:
    fontFamily: Saira
    fontWeight: 600
    fontStretch: 80%
    fontFeature: tnum
    fontSize: 1.875rem
    lineHeight: 1
  plate:
    fontFamily: Saira
    fontWeight: 600
    fontStretch: 80%
    fontFeature: tnum
    fontSize: 1.25rem
    letterSpacing: 0.02em
rounded:
  sm: 6px
  md: 8px
  lg: 12px
  xl: 18px
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
    textColor: "{colors.sidebar-text}"
    borderColor: "{colors.sidebar-border}"
  nav-link-active:
    backgroundColor: "{colors.sidebar-active}"
    textColor: "{colors.sidebar-active-text}"
    rounded: "{rounded.md}"
  banner:
    backgroundColor: "{colors.banner}"
    textColor: "{colors.banner-text}"
    borderColor: "{colors.banner-border}"
    rounded: "{rounded.lg}"
  cluster:
    backgroundColor: "{colors.banner}"
    textColor: "{colors.banner-text}"
    borderColor: "{colors.banner-border}"
    rounded: "{rounded.xl}"
  voice-bar:
    backgroundColor: "{colors.banner-raised}"
    textColor: "{colors.banner-muted}"
    borderColor: "{colors.banner-border}"
    rounded: "{rounded.full}"
  copilot-line:
    backgroundColor: "{colors.banner}"
    textColor: "{colors.banner-muted}"
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

**Creative North Star:** "Màn hình thứ hai của xe, có trợ lý". Home opens like the screen behind the steering wheel: two gauges drawn to scale, the car, a row of tell-tale lamps that light from real states, and a voice bar where the assistant speaks first. Everywhere else the app stays light (cool titanium ground, white cards) for daylight phone use, inside an ink sidebar frame, and the assistant speaks through one thin ink copilot line when it has something real to say. Futuristic through instruments and foresight (Saira, gauges, a start-up self-test, an assistant that has already checked), never through glow.

**Product context:** Vietnamese-language web app (React 19 + Tailwind v4) for private VinFast owners: maintenance due status, AI assistant, cost estimate, booking. The Workshop Portal (technicians) shares the same shell. The real competitor is the official VinFast app.

**Roles:** exactly two user roles, the vehicle owner (Chủ xe) and the workshop owner (Chủ xưởng). "Technician" / "Kỹ thuật viên" in screens, wireframes and the `/technician/*` routes means the workshop owner, the `workshop_owner` account in specs and API. It is not a third role. UI copy may say "Kỹ thuật viên"; specs and permission rules say "Chủ xưởng". See PRD §4.

**Mode per surface:** Owner app and Workshop Portal are Operate surfaces. Login is the one Persuade surface.

**Layout is fixed.** This system restyles the existing structure (240px sidebar, 64px topbar, card grid, booking flows). It does not move screens, menus or flows. Layout changes need their own decision.

**Approved reference:** `/design-consultation` 2026-10-12, merged preview "EV Care Bản ghép" (https://claude.ai/artifact/AJd4VNVauKEUNr5La2HDXK), built from two HTML previews: the Home cluster, tell-tales and self-test from B "EV Care Màn hình thứ hai" (https://claude.ai/artifact/XXBzGAeJ6inRKEybg8UdKq); the copilot line, ink sidebar, assistant cyan, Saira and titanium neutrals from A "EV Care Buồng lái" (https://claude.ai/artifact/R29HaBgHE8Dq8Mxc1oHDzt). B's Chakra Petch was not taken (see Typography). Earlier: `/design-shotgun` 2026-10-04 (`~/.gstack/projects/<slug>/designs/dashboard-refresh-20261004/`), shell from variant A "Showroom sáng", Home banner from variant B "Buồng lái đêm".

**Key characteristics:**
- The real EV CARE logo in the sidebar (ink parts follow light/dark mode), login, splash, onboarding and favicon.
- Sidebar follows light/dark mode; cool titanium ground, white cards with soft shadows and 1px hairlines in light mode.
- Home opens on the instrument cluster: km gauge · the car with plate and ODO · days gauge, tell-tale lamps, and the assistant's voice bar.
- On other pages the assistant speaks in one ink copilot line, only with real figures.
- Saira for headings, readouts, gauges and plates; Inter for everything you read.
- Solid green buttons with white text. No gradients, no coloured glows.
- Licence plates drawn as real plates.

## Colors

**Strategy:** Restrained. Ink and one green (from the logo family) on cool titanium neutrals. Warning and error are the only other hues on light surfaces. Cyan (`assistant-signal`) exists only on ink and only for the assistant's voice.

**Light or dark:** Light is the default (owners open the app on phones in daylight; Demo Day projectors favour light). Dark is a full alternative under `:root[data-theme='dark']`, stored per browser in `localStorage` key `evcare.theme.v2`.

**Rules:**
- `--color-emerald` / `--color-brand` `#007A52` is the action green for text, icons and fills; white text on it is 5.38:1. In dark both become bright greens (`#3AD493` text, `#19C37D` fill) with near-black text on fills.
- `--color-logo-bolt` (`#00A86B`, dark `#19C37D`) is only for the bolt inside the logo. Never use it for text on light surfaces (3.08:1).
- Banner tokens (`banner-*`) are ink in both themes. On the banner, muted text is `#94A0AC` (6.71:1), the accent button is `#19C37D` with `#0A0E13` text (8.43:1), and readouts that caused the due alert turn amber (`amber-400`).
- `bg-brand-gradient` still exists for old class lists but paints solid `--color-brand`; `text-brand-gradient` paints solid `--color-emerald`; `glow-emerald` and `bg-app-backdrop` are no-ops. New code uses `bg-brand`, `text-emerald` directly.
- Plates stay white with ink in both themes. Dark error is `#F87171` for legible small text.
- `assistant-signal` `#22C7DD` (9.3:1 on `#0B1218`) marks the assistant on ink: its live dot, its uppercase label, the scan line while it works, and the robot's eyes on ink. Never on light surfaces, never for actions (actions on ink stay `banner-accent` green), never as a fill behind text.
- Sidebar tokens (`sidebar-*`) follow the theme: white with dark text in light mode, ink with light text in dark mode. Active rows use `sidebar-active` with `sidebar-foreground` text and a `sidebar-active-foreground` icon; count badges use `brand` with `on-brand` text. Workshop suffixes use `emerald` on `emerald-dim`, and logout hover uses `error`.
- `banner-raised` `#16212B` is the one step up on ink: the active nav row, the robot disc, gauge tracks, the voice bar.
- Tell-tale lamps use only these colours on ink: `banner-accent` green (fine), `banner-alert` amber (needs you), `banner-danger` `#F87171` red (overdue or safety), `lamp-off` `#2E3A44` (nothing to report; icon only, the label stays `banner-muted` so it is readable). Lit amber and red labels use `banner-text`. Colour is never the only signal: the label states the condition ("Đã quá mốc bảo dưỡng").
- Gauge fills follow the backend's due status, never the arc length (BR-008): green, amber on the axis that made it DUE_SOON / OVERDUE (`dueReason`), red once that axis is past the milestone. The last 10% of each track is a faint amber zone, like the red line on a rev counter.

## Typography

Two families from one Google Fonts request in `frontend/src/styles/index.css`: `Inter:opsz,wght@14..32,300..800` and `Saira:wdth,wght@75..125,300..800`. Both ship a Vietnamese subset (Saira verified 2026-10-12 against the css2 response; Inter 2026-10-11). Inter stays the reading face (chosen 2026-10-11 to match tesla.com). Saira, a squarish technical sans with a width axis, is the instrument voice: wide for headings, condensed for figures, like the lettering on an EV cluster. Sora and Oxanium were rejected for missing Vietnamese.

- **`font-display`** (Saira 700, `wdth` 112, -0.01em; every `h1` gets it from the base layer): page titles 24–30px, card titles that name a place (vehicle name, page sections), the car name in the cluster. Not for buttons, labels, body or table text.
- **`font-plate`** (Saira 600, `font-stretch: 80%`, `tnum`): gauge figures, the cluster ODO, readouts in ink panels and summary strips (km, days, kWh, short money like "6,42 tr"), licence plates (`PlateTile`). Units stay Inter at ~40% of the figure size.
- Chakra Petch (preview B) was rejected for the figures: its digits are proportional (advance widths 366–636 units) and it has no `tnum` feature, so rolling numbers would jitter and columns would not align. Checked 2026-10-12 from the Google Fonts TTF.
- **Inter** (`font-sans`, 300–800): body 14px, labels 13px semibold, nav, buttons, tables; sentence case.
- **`font-mono`** (Inter + `tnum`): prices and dates in rows and tables, timestamps, VIN, booking codes, and the uppercase instrument labels on ink (11px, 0.08em tracking).
- Fallback: `font-display` and `font-plate` fall back to Inter; the layout must hold with Saira missing (widths are checked at 80% and 100% stretch).

## Layout

Shell unchanged: 240px sidebar (drawer below `lg`), 64px topbar, content padding `p-4 sm:p-6 xl:p-8`. On `sm`–`lg` the topbar shows the logo because the sidebar is hidden.

**Home (changed 2026-10-12):** greeting → `HomeCluster` (full content width) → trip row of three cards (`xl:grid-cols-3`, `md:grid-cols-2`, one column on phones): Lịch hẹn tới, Chi phí 12 tháng, Thông số & bảo hành → Lịch sử dịch vụ gần đây (full width). Removed from Home because the cluster now carries them: `HomeCarousel`, `HomeHighlights` (folded into "Lịch hẹn tới"), `VehicleOverview` (car, plate, ODO and milestone are in the cluster), the AI card (the voice bar), and `QuickActions` (each card carries its own action). The cluster lays itself out by its own width (container query at 720px), not the viewport: three columns above, car on top with the two gauges side by side below.

Owner page widths (`shared/ui/page.ts`, `page(width)`): **full** for pages that fill the content area (Dashboard, Xe của tôi, Lịch sử dịch vụ, Chi phí bảo dưỡng, Đặt lịch, Hỗ trợ, Thông báo; Lịch hẹn của tôi is reading width below xl and full with its rail); **reading** `max-w-3xl`, left-aligned, for single-column lists, details and forms (Báo giá, cài đặt Thông báo, Đổi lịch, So sánh xưởng); **ticket** `max-w-xl` centred for one card (vé lịch hẹn, hỏi thăm sau bảo dưỡng). Loading and error states keep the width of their page.

Owner **Thông báo**: a full-width list grouped into Hôm nay / Trước đó, beside a 320px rail at `xl`. The rail contains **Việc cần xử lý** (up to three entries, prioritized by safety/overdue, decisions, appointment reminders, then other pending work) and **Nhắc bảo dưỡng** (live settings summary and link). Counts reflect business state, including unresolved maintenance reminders without an unread flag; settled items leave the rail. The rail stacks below the list on smaller screens. Loading and errors retain both columns without claiming there is no pending work. The workshop notification page keeps its reading width and does not fetch owner settings. Approved from `artifacts/notifications-preview.html` on 2026-10-12.

## Elevation & Depth

- `elevation-sm`: `0 1px 2px` ink 4% + `0 8px 24px -16px` ink 18% for cards and inputs.
- `elevation-md`: dialogs, drawers, toasts, card hover.
- The cluster, the vehicle hero, the copilot line and the sidebar have no shadow; ink fill and a `banner-border` hairline give them weight. Lamps and gauges never glow.
- The topbar is the only translucent layer: surface at ~78% with a 14px backdrop blur, so content scrolling under it stays legible as depth. No other glass.
- No coloured halos, no radial page glows, no decorative blur blobs.

## Shapes

Tighter radii read as precision. Tailwind radius tokens are overridden: `rounded-xl` = 8px (buttons, inputs, nav items, chips, readout grid), `rounded-2xl` = 12px (cards, vehicle hero, copilot line), `rounded-3xl` = 18px (the Home cluster, dialogs, login card, chat composer). Status badges, avatars, ink chips and the voice bar stay `rounded-full`. Plates use 6px.

## Components

- **Logo** (`shared/ui/Logo.tsx`): inline SVG from `public/brand/ev-care-logo.svg`. Ink parts use `currentColor` (`text-foreground` / `text-sidebar-foreground` on light, `text-banner-foreground` on ink); the bolt uses `--color-logo-bolt`. `variant="mark"` for tight spots. Favicon: white mark on an ink rounded square.
- **Sidebar** (`layouts/AppLayout.tsx`): follows light/dark mode (`bg-sidebar`, `border-sidebar-border`), with the logo in `text-sidebar-foreground` and the green bolt. Inactive items use `text-sidebar-muted` with `hover:bg-sidebar-hover`; active items use `bg-sidebar-active text-sidebar-foreground` with a `sidebar-active-foreground` icon and a 1px `sidebar-border` inset. Count badges use `bg-brand text-on-brand`. The mobile drawer uses the same theme tokens. The topbar logo (below `lg`) follows `text-foreground`.
- **HomeCluster** (`features/dashboard/components/HomeCluster.tsx`, replaces `HomeCarousel` on Home): one ink panel (`cluster`, 18px radius, 18–22px padding). Top row: data freshness on the left ("Dữ liệu hãng lúc 08:06 12/10", from `odometer.recordedAt`; a retry while it fails) and "Chi tiết xe" to `/vehicle` on the right. Main row: km gauge · car · days gauge. Then the tell-tale row, then the voice bar. Real data only; every part has an empty state (see Gauge, Tell-tales, Voice bar).
- **Gauge** (`shared/ui/Gauge.tsx`): SVG, 240° sweep from lower-left to lower-right, 41 ticks (every 10th major), 10px track in `banner-raised`, faint amber last-10% zone, fill and end cap per the lamp colours. The figure sits in the centre (`font-plate`, 28–40px) with its unit and a caption under it. Both gauges start at the latest periodic service from the service records (`lastPeriodicService`), not `status.lastService`, which can be a repair. Left gauge: km from that visit (or 0 km at delivery) to the next milestone, current km taken from the backend's `remainingKm` ("1.240 · km tới mốc · Mốc 20.000 km", ends "10.000 / 20.000"); past the milestone it reads "320 · km quá mốc" in red. Right gauge: days from that visit to the due date ("23 · ngày tới hạn · Hạn 04/11/2026", ends as dd/mm/yy because they can share a day and month); without a periodic visit the figure stays and the arc is empty. Unknown milestone or basis: empty track, "—", caption "Chưa đủ dữ liệu", and the trip row's "Lịch hẹn tới" card offers "Đặt lịch". The SVG is `aria-hidden`; the figure and caption are the accessible text. Drawn to scale: the fill is (value − start) / (end − start), clamped.
- **Car (cluster centre)**: model photo from `public/vehicles/<model>.webp` on the ink stage with a 1px floor line, car name in `font-display` beside `PlateTile`, ODO in `font-plate` 28–34px with "km", and the source line "Hãng cập nhật lúc …" in `banner-muted`.
- **Tell-tales** (rendered in `HomeCluster`, states from `tellTales` in `features/dashboard/components/clusterLogic.ts`): a row of lamp links under a hairline, each a lucide icon + short label, each linking to its page. Lamps and their sources: Bảo dưỡng (`Wrench`; amber when the maintenance status is alerting, red past the milestone), Báo giá (`FileClock`; amber with quote results the owner has not seen, only while quotes are in the nav), Lịch hẹn (`CalendarCheck`; green with an upcoming confirmed booking, amber while it waits for the workshop, opens the ticket), Bảo hành (`ShieldCheck`; green while `isActive`, amber when `warrantyTimeline` says ending, i.e. under 6 months), ODO (`Gauge`; amber when the backend marks `odometer.isStale`, because the km gauge would be wrong). During the self-test off lamps light amber. No lamp without a data source: the recall lamp in preview B waits for one. Off lamps hide below the 720px container width. `role="list"`; each lamp's label carries its state.
- **Voice bar** (inside the cluster): the assistant's one place on Home, a `rounded-full` `banner-raised` bar with the robot disc. When the assistant has a real proposal it speaks first (`voicePrompt`): today that is a DUE_SOON / OVERDUE milestone with nothing booked, said with the backend figures ("Mốc 24.000 km / 24 tháng: còn 600 km · 12 ngày. Mình tìm xưởng và giờ trống gần bạn nhé?") with a cyan "Trợ lý" label and live dot and one `banner-accent` button "Đặt lịch nhanh" to quick booking. When workshop slot data reaches Home, the sentence can name the slot and the estimate ("Giữ chỗ"). Otherwise it shows one suggested question ("Hỏi xe của bạn: “Mốc 20.000 km gồm những gì?”") that opens `/ai?q=…`. The trailing button is an arrow, not a microphone: the assistant has no voice input. While the proposal is computed, the scan line runs along the bar's top edge.
- **Trip cards** (Home, below the cluster): Lịch hẹn tới (the upcoming booking with time and workshop, or "Chưa có" with the milestone sentence and "Đặt lịch" primary + "Ước tính chi phí" secondary), Chi phí qua EV Care · 12 tháng (recorded `actualCost` only, `monthlySpend`; total in `font-plate` and a month bar chart drawn to scale: axis 0 to the year's max, gridline at half, zero months as 2px stubs, the latest paid month in `primary`, the others in a neutral bar colour), Thông số & bảo hành (battery kWh, motor kW, model year, and the time-used bar of the battery warranty, else the one that ends last, from `warrantyTimeline`). File: `TripCards.tsx`.
- **Copilot line** (`shared/ui/CopilotLine.tsx`): the assistant on light pages. One ink strip (`rounded-2xl`, 12px padding): robot disc, a cyan uppercase label ("Trợ lý gợi ý"), one sentence with the real figure in `banner-text`, one ghost action. At most one per page, only from real data; hidden when there is nothing to say. Wraps under 640px with a full-width button. Placed so far on Lịch sử dịch vụ (`historyCopilot`: while the milestone is DUE_SOON / OVERDUE, its item and warranty counts, "Xem chi phí dự kiến"). Chi phí bảo dưỡng and Báo giá get one when a rule with real figures is agreed.
- **Carousel** (`shared/ui/Carousel.tsx`): no longer used on Home; keep it only while another screen uses it, otherwise remove it with `HomeCarousel` and `homeSlides.ts`. One ink panel; slides stack and crossfade over 700ms. Autoplay 6s with a filling dot, pauses on hover, focus and the pause button. No autoplay under `prefers-reduced-motion`; swipe on touch; inactive slides are `inert`. Controls (dots, pause, prev/next) sit inside the panel, bottom edge. A single slide renders without controls.
- **HomeCarousel** (retired from Home 2026-10-12, replaced by `HomeCluster`): slides only from real data or real features (`homeSlides.ts`): maintenance (known milestone; readouts for km and days left, from `sm` up), booking (only when nothing is upcoming), assistant (always, with suggested questions from `sm` up). No promotional slide until there is a real source of offers.
- **Login brand panel** (`AuthBrandPanel.tsx`): banner tokens, white logo, green highlight phrase.
- **PlateTile** (`shared/ui/PlateTile.tsx`): white plate, ink border, `font-plate`; colours from the `plate` / `plate-ink` tokens (`bg-plate text-plate-ink border-plate-ink`), which have no dark override.
- **VehicleHero** (`features/vehicles/components/VehicleHero.tsx`): the ink panel of Xe của tôi, built from banner tokens like the Home cluster: mono uppercase labels, name, PlateTile, masked VIN, a readout grid (ODO, next milestone in `amber-400` when km caused the alert, battery, motor) and the model photo on the ink stage. Below it: maintenance card (2/3) beside ODO and last-service cards, then warranty tiles with a time-used bar (`warrantyTimeline`, display only; `isActive` from the backend decides the status).
- **Buttons**: primary `bg-brand` + `text-on-brand`; secondary card + border; danger error text and border.
- **Context rail** (xl and up, `shared/ui/RailRow.tsx` rows): owner pages with spare width put the main column in 2/3 and one card of real data in 1/3, like the Dashboard grid. Booking wizard: `BookingSummaryRail` (vehicle, milestone with items and warranty marks, workshop, time; "Đổi" jumps back a step; sticky; the confirm card hides those rows at xl and keeps cost, note, timer and buttons). Lịch hẹn của tôi: a row opens `BookingPreview` (QR, time, workshop with directions, items, cost, "Đổi lịch", link to the ticket; not sticky because the QR makes it taller than the screen; cancelling stays on the ticket page). Lịch sử dịch vụ: `HistorySummary` strip at every width (periodic visits, latest visit, EV Care spend, next milestone with "Đặt lịch"), and at xl a row opens `ServiceRecordDetail` while the Nguồn and booking-link columns move into it. Below xl the rails are hidden and the pages behave as before.
- **Quick actions**: green-tint icon tile (`bg-emerald-dim text-emerald`) beside the label from `sm` up. Not on Home since 2026-10-12.
- **Robot mascot** (`shared/ui/RobotAvatar.tsx`): the AI assistant's face. White head with ink outline, ink face screen, `#19C37D` eyes (`assistant-signal` cyan when the robot sits on ink), `#007A52` ears, pink cheeks; fixed colours in both themes like PlateTile. Moods: `idle` (message avatar), `thinking` (amber antenna light while streaming), `happy`, `wave` (empty chat). `RobotAvatar` puts it on an `bg-emerald-dim` disc, with an optional online dot. It stands for the assistant only: chat, and "Hỏi trợ lý" buttons that open it.
- **PhotoUploadTile** (`shared/ui/PhotoUploadTile.tsx`): 72px `rounded-xl` tile, border `{colors.border}`, error border `{colors.error}` with "Tải lại" below; a progress ring over the preview while uploading; `PhotoAddTile` is the dashed "Thêm ảnh" tile that opens the camera on phones (`capture`). Hidden at three photos.
- **DecisionSheet** (pattern, not a component): the `Dialog` (bottom sheet at 390px, `rounded-3xl`) that confirms a money decision, e.g. "Thêm {hạng mục} · {giá}? Tổng mới {tổng}"; its confirm button is `button-primary`, "Huỷ" is secondary. Declining a safety item uses the same sheet as `alertdialog` with a danger button.
- **Decision rows** (`features/bookings/components/DecisionCard.tsx`): lines in one card with `divide-y divide-border`, no nested cards, no coloured left border; prices `font-mono`; safety items carry a warning `Badge` with `ShieldAlert` and the text "Hạng mục an toàn"; photo thumbnails 56px `rounded-xl`, tap to open large.
- **Chat** (`features/assistant`): user bubbles `bg-brand text-on-brand`, 22px radius with a 6px tail corner; assistant answers in `bg-card elevation-sm` cards with no border; sources as pills under a hairline; composer is a floating `rounded-3xl` card with a round send button; proposal card has a green-tint header and a calendar date tile.

## Do's and Don'ts

- Do use `bg-brand` + `text-on-brand` for primary fills and `text-emerald` for green text.
- Do render the real logo through `<Logo />` and plates through `<PlateTile />`.
- Do keep one large ink block per page at most (Home cluster, Xe của tôi hero), with real data only. The ink sidebar is the frame and does not count; one copilot line is allowed on a page, also beside the large block.
- Do let the assistant speak only with something real to say: a figure, a date, a slot, an estimate. No "Mình có thể giúp gì?" filler in the voice bar or copilot lines.
- Do give every gauge, lamp and readout a data source and an empty state; never show a figure EV Care does not have (no battery %, no range: there is no live link to the car).
- Do check both themes and 390px width before merging UI changes.
- Do leave keyboard focus to the shared ring: links, buttons and `[tabindex]` get a 2px emerald outline (`focus-ring`, offset 2px) from the base layer; fields use `focus-field` (emerald border + 4px soft ring). Don't add per-component focus rings or `outline-none` on controls.
- Do give touch controls a 44px target: topbar icon buttons (`ICON_BUTTON`) are 36px with a mouse and 44px under `pointer-coarse`.
- Don't use gradients, glows, blur blobs or gradient text.
- Don't use mono uppercase labels outside ink (Home cluster, vehicle hero, copilot line, sidebar); elsewhere labels are sentence case.
- Don't make lamps or gauges glow, pulse, or blink at rest; a lamp is lit by colour alone.
- Don't use `assistant-signal` cyan on light surfaces, for actions, or for anything that is not the assistant.
- Don't set body, buttons or table text in Saira; it is for headings, readouts and plates.
- Don't use the logo green `#00A86B` as text on light surfaces.
- Don't change layout or navigation as part of a visual change.

## Motion

- **Approach:** intentional. Motion says "data changed" or "the assistant is working", nothing else.
- **Durations:** 150–200ms for hover and colour, 450ms ease-out card rise (6px, from 55% opacity, never from 0) staggered 40ms, 600ms ease-out readout roll, 1.5s cluster self-test.
- **Readout roll:** when a readout's value changes (and on first load), the figure counts from the previous reading to the new one with `tnum`, so widths never jump. Rolls from the last known value, never from 0.
- **Assistant working:** a 2px `assistant-signal` scan line sweeps the top edge of the voice bar or copilot line (1.1s loop) and the robot's antenna turns amber; replaces spinners on assistant surfaces. Chat's "Đang tra…" row uses the same line.
- **The one authored moment:** the cluster self-test, like switching the car on. On the first Home render of a browser session (`sessionStorage` key `evcare.cluster.selftest`): every lamp lights in its own colour, both gauges sweep to full in the first 45% and settle on their values, the ODO rolls from the previous reading; at 40% the lamps drop to their real states. Not replayed on later visits in the same session.
- Everything respects `prefers-reduced-motion`: no self-test, no rise, no roll (final values at once), the scan line becomes a static full-width line.

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
| 2026-10-08 | Xe của tôi: ink hero (variant B) replaces the identity card; layout becomes hero → maintenance (2/3) + ODO/last service → warranty tiles | User chose variant B on the design canvas; specs moved into the hero readouts, warranty table became tiles with remaining time. |
| 2026-10-08 | AI assistant restyle: robot mascot avatar, green user bubbles, borderless answer cards, floating composer, starter cards on the empty chat | User found the chat plain and asked for a cute robot avatar; approved on the design canvas. Layout (chat column + 320px vehicle panel) unchanged. |
| 2026-10-09 | Quyết định về tiền: hai nút cùng trọng lượng trên dòng ("Đồng ý" / "Không làm", cả hai `button-secondary`, "Đồng ý" có icon `Check` xanh); nút chính chỉ trong bước xác nhận (DecisionSheet) | Chủ xe không bị đẩy về phía đồng ý; bước xác nhận mới là chỗ cam kết tiền (bao-gia-hai-tang 12A). |
| 2026-10-09 | Workshop Portal thêm mục "Bảng giá" (`/technician/price-list`) dưới "Sức chứa" | Màn mới cho chủ xưởng tự quản lý giá (bao-gia-hai-tang D14); thứ tự các mục cũ giữ nguyên. |
| 2026-10-10 | Home banner (maintenance slide): from `sm` the headline is the milestone only; the readouts carry the km/days figures. Phones keep the figures in the headline | The same "quá X km · quá Y ngày" appeared in the headline, the readouts and the Bảo dưỡng card. (design review FINDING-010) |
| 2026-10-10 | Login below `lg`: logo, then the brand panel's headline (highlight in `text-emerald`) and promise above the form (`AuthMobileBrand`) | Phones showed only the logo and "Đăng nhập" on the Persuade surface. (design review FINDING-014) |
| 2026-10-10 | Workshop Dashboard: the four icon-tile KPI cards become one strip of count links (label + mono figure, `warning` when a count needs action); same place, same links | Tall icon tiles for single digits read as AI-dashboard filler. (design review FINDING-015) |
| 2026-10-11 | Owner screens Đặt lịch bảo dưỡng, Lịch hẹn của tôi and Lịch sử dịch vụ get a context rail at xl (2/3 + 1/3); history also gets a summary strip | On wide screens these pages left half the width empty. User approved the right-rail preview (artifact "Cột phải EV Care"). Real data only; no rail below xl. |
| 2026-10-11 | Font: Inter everywhere (replaces Be Vietnam Pro, JetBrains Mono, Barlow Condensed); banner readouts 26px with a small unit | User asked for tesla.com's look; Universal Sans is proprietary. Inter is ~40% wider than Barlow Condensed, so "12.500 km" wrapped at 2.15rem. |
| 2026-10-11 | Owner sidebar "Hỗ trợ" becomes a NavLink to `/support` (active state like nav items); the page shows the booked workshop's contact (2/3), the AI question box in the right rail, and the FAQ. Workshop Portal keeps `SupportLink` | The button only showed a "đang cập nhật" toast. User asked for the page; support tickets stay out of scope (PRD v3.7), so it gathers existing channels only. |
| 2026-10-12 | Owner pages use three widths through `page()`: full, reading (`max-w-3xl`, left) and ticket (`max-w-xl`, centred); Xe của tôi drops `max-w-6xl`, Đổi lịch is no longer centred, loading states match their page | Pages used five widths (880 / 944 / 976 / full) and mixed centred with left-aligned. User chose the three-tier rule. (design review FINDING-016) |
| 2026-10-12 | One focus ring for controls (`focus-ring`, the base outline) and one for fields (`focus-field`); topbar icon buttons 44px on touch; PlateTile uses the `plate` tokens | About five ring recipes (ring-2/ring-4, /25 /40 /50, with and without offset) and 36px touch targets. (design review FINDING-012) |
| 2026-10-12 | Direction "Buồng lái có trợ lý" replaces "Showroom sáng": assistant brief leads the Home banner and a copilot line speaks on light pages (R1); Saira for headings, readouts and plates (R2); ink sidebar in both themes (R3); `assistant-signal` cyan on ink only (R4); titanium neutrals; radii 8/12/18; readout roll, card rise, scan line. Layout, money rules, focus rings and page widths unchanged | User asked for a more futuristic UI and named "trợ lý AI chủ động" as the thing to remember; approved the HTML preview (artifact R29HaBgHE8Dq8Mxc1oHDzt) with all four risks via /design-consultation. Partly reverses 2026-10-11 "Inter everywhere": Inter stays for reading, Saira takes the instrument roles. Cyan is not the retired emerald→cyan gradient: solid, ink-only, assistant-only. |
| 2026-10-12 | Merge of A and B: Home opens on `HomeCluster` (km gauge · car · days gauge, tell-tale lamps, voice bar) and the trip row; `HomeCarousel`, `HomeHighlights`, `VehicleOverview`, the AI card and `QuickActions` leave Home. Other pages keep A: copilot line, ink sidebar, cyan, Saira, titanium neutrals. New tokens `banner-danger`, `lamp-off`; the self-test replaces "Kiểm tra lại" as the authored moment | User compared preview A (assistant first) and B (the car's second screen) and asked for B's cluster on Home with A's copilot line elsewhere. Saira kept over B's Chakra Petch because Chakra Petch has proportional digits and no `tnum`. Lamps only for states EV Care knows; no battery %, no range, no recall lamp until a source exists. Home layout change approved with this merge. |
| 2026-10-04 | Workshop › Sức chứa cells lead with seats left (16px mono); booked and locked lines only when non-zero; full slots read "Hết chỗ" | 56 identical three-line 11px cells hid the few slots that mattered. (design review FINDING-018) |
