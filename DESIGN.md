---
name: Flotta
description: Contrôle avant départ et exploitation de flotte poids lourds, sobre et neutre, un seul accent indigo.
colors:
  accent: "#4054d6"
  accent-hover: "#3343b4"
  accent-pressed: "#2a3796"
  accent-soft: "#eceefc"
  page: "#f6f7f9"
  surface: "#ffffff"
  surface-sunken: "#f1f2f6"
  border: "#e1e4ea"
  border-strong: "#c9ced9"
  ink: "#14171f"
  ink-2: "#444b5b"
  ink-3: "#667085"
  neutral-chip: "#eceef2"
  ok: "#14663f"
  ok-bg: "#e4f4ea"
  warn: "#7a4f00"
  warn-bg: "#fcefd0"
  danger: "#b3261e"
  danger-bg: "#fdeae8"
typography:
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.5
  caption:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.5
  driver-body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.35
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    height: "36px"
    padding: "0 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-primary-active:
    backgroundColor: "{colors.accent-pressed}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "36px"
    padding: "0 14px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-sunken}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.md}"
    height: "36px"
  button-xl:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    height: "56px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "36px"
    padding: "0 12px"
  badge-ok:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
    rounded: "{rounded.pill}"
    padding: "2px 10px 2px 8px"
  badge-warn:
    backgroundColor: "{colors.warn-bg}"
    textColor: "{colors.warn}"
    rounded: "{rounded.pill}"
  badge-danger:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger}"
    rounded: "{rounded.pill}"
  badge-neutral:
    backgroundColor: "{colors.neutral-chip}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.pill}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "20px"
  nav-item-current:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-pressed}"
    rounded: "{rounded.md}"
    height: "36px"
  plaque:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
---

# Design System: Flotta

## Overview

**Creative North Star: "Le Registre de Garage"**

Flotta plays the category standard straight for B2B SaaS: cool neutral greys, a single indigo accent, system UI type, tabular numerals, Lucide icons. It is light only, because the office is daylit and drivers work outdoors. Nothing performs; the interface is a legible ledger where the question "which trucks can leave?" is answered at a glance.

Two registers share one set of tokens. The operator shell is dense and calm: a 240px sidebar, white panels on a pale grey page, 36px controls, 15px text. The driver page is the same system scaled for thumbs, gloves and sunlight: 17px text, 52-56px targets, 1.5px borders, a fixed bottom submit bar.

State is never carried by color alone. Every green, amber or red appears with a Lucide icon and a word.

**Key Characteristics:**
- Cool grey page, white surfaces, hairline borders; depth is mostly borders, not shadows.
- One accent (indigo) for primary action, focus, current navigation and selection.
- Semantic trio (green, amber, red), each as a text color on a tinted fill, always with icon plus label.
- System font stack at modest sizes; weights 550 to 650 do the hierarchy work.
- Tabular numerals on tables and plates.
- No dark mode (`color-scheme: light`).

## Colors

A cool, near-neutral grey ground with one saturated indigo and three desaturated state colors.

### Primary
- **Signal Indigo** (#4054d6): primary buttons, links, focus ring and outline, caret, selection, checked switch, brand mark, drop-zone hover border.
- **Deep Indigo** (#3343b4): hover for primary buttons and links. Pressed state and text on indigo tint is #2a3796.
- **Indigo Mist** (#eceefc): current navigation item background and accent badge.

### Neutral
- **Cool Paper** (#f6f7f9): page background.
- **White Sheet** (#ffffff): panels, sidebar, inputs, dialogs.
- **Sunken Grey** (#f1f2f6): table headers, hover fills, signature box.
- **Hairline** (#e1e4ea): panel and row dividers. **Firm Hairline** (#c9ced9): control borders, scrollbars, switch track.
- **Ink** (#14171f): primary text. **Ink Secondary** (#444b5b). **Ink Tertiary** (#667085): hints, table headers, muted metadata.
- **Quiet Chip** (#eceef2): neutral badge ("Non contrôlé").

### Semantic
- **Cleared Green** (#14663f on #e4f4ea): contrôlé, success alerts, OK segment.
- **Caution Amber** (#7a4f00 on #fcefd0): défaut, warning alerts.
- **Stop Red** (#b3261e on #fdeae8): bloqué, critical defect, destructive actions, KO segment.

### Named Rules
**The One Indigo Rule.** Indigo means "act here" or "you are here". It never encodes status.
**The Never Color Alone Rule.** A state is color plus icon plus text; the badge and alert components enforce it.

## Typography

**Display Font:** none. **Body Font:** system UI stack (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial`). No webfont is loaded.

**Character:** neutral and native; it looks like the user's own OS, which suits a tool used all day.

### Hierarchy
- **Headline** (650, 22px, 1.25, -0.01em): page titles (h1); balanced wrapping.
- **Title** (650, 16px, 1.3): panel headings (h2); 14px/650 for h3.
- **Body** (400, 15px, 1.5): default text. Driver surface 17px.
- **Label** (550, 14px): field labels, buttons, tabs, nav.
- **Caption** (600, 13px): table headers, badges; hints at 13px/400.
- Driver: h1 result 24px, h2 18px, plate 24px/650.

### Named Rules
**The Tabular Rule.** Tables, counts, times and plates use tabular numerals.

## Layout

Operator pages sit in a two-column grid: 240px sticky sidebar plus a main column capped at 1180px with 32px/40px padding. Under 860px the sidebar becomes a sticky top bar with horizontally scrolling nav; under 560px nav shows icons only (40px squares). Tables under 640px collapse into stacked cards so no column hides off-screen. The detail page is a 1.4fr/1fr grid collapsing at 960px. Driver pages are a single 560px column with 16px side padding and 120px bottom room for the fixed submit bar.

Spacing is a 4-based rhythm in practice: 8 / 12 / 16 / 20 / 24 gaps; panel bodies 20px; table cells 12px 16px; stacks 16px (24px for large).

## Elevation & Depth

Mostly flat: hierarchy comes from white panels with 1px hairlines on a grey page. Shadows are minimal and structural.

- **Resting** (`0 1px 2px rgba(20,23,31,.06), 0 1px 1px rgba(20,23,31,.04)`): panels, secondary buttons, selected tab.
- **Overlay** (`0 12px 32px rgba(20,23,31,.14), 0 2px 8px rgba(20,23,31,.08)`): dialogs only.
- Fixed driver submit bar: `0 -4px 16px rgba(20,23,31,.06)` over a 96% white fill.

### Named Rules
**The Flat Until Floating Rule.** Only dialogs get the overlay shadow; everything else is border-defined.

## Shapes

Gently rounded: 8px controls, 12px panels, dialogs and driver cards, 6px plates, full pills for badges and switches. Driver segmented buttons use 10px, the XL button 12px. Borders are 1px (1.5px on the driver page for outdoor legibility). Focus is a 2px indigo outline with 2px offset; fields swap to a 3px indigo 20% halo.

## Components

### Buttons
- **Shape:** 8px radius, 36px high (30px small, 32px icon-only), 16px icons, 8px gap.
- **Primary:** Signal Indigo fill, white text. Hover Deep Indigo, pressed #2a3796.
- **Secondary (default):** white, firm hairline, resting shadow; hover Sunken Grey.
- **Danger:** red text, soft red border; hover red tint. **Ghost:** transparent, secondary ink.
- **XL (driver):** full width, 56px, 18px text, 12px radius. Disabled: 50% opacity.

### Inputs / Fields
- 36px high, white, firm hairline, 8px radius; hover border #9aa2b3; focus indigo border plus halo. Driver variant 52px, 17px text. Switch: 34x20 pill, indigo when on. Labels 14px/550 above, hints 13px below.

### Badges and alerts
- Pill badges with 14px icon and 13px/600 text: ok, warn, danger, neutral, accent. Status mapping: Contrôlé = check circle (green), Non contrôlé = clock (neutral), Défaut = triangle alert (amber), Bloqué = octagon alert (red). Alerts are bordered 8px-radius blocks with an 18px icon.

### Tables
- Sunken header (13px/600, tertiary ink), 12px 16px cells, hairline row dividers, hover #fafbfc, cell links bold ink turning indigo on hover.

### Navigation
- Sidebar items 36px, icon 18px plus label; current page gets Indigo Mist fill, #2a3796 text, indigo icon via `aria-current="page"`.

### Plaque (signature)
- License plate rendered as a bordered, white, 650-weight tabular chip with 0.04em tracking; 24px with 2px ink border on the driver page.

### Driver checklist point
- Card with 1.5px border, 12px radius; KO state turns the border red with a faint red fill. OK/KO segmented control, 52px minimum height, icon plus word, tinted when selected.

## Do's and Don'ts

### Do:
- **Do** pair every state color with a Lucide icon and a text label.
- **Do** keep indigo for actions, focus and current location only.
- **Do** use tabular numerals for figures and plates.
- **Do** size driver controls to at least 52px with 1.5px borders and 17px text.
- **Do** keep light mode only.
- **Do** use the system stack and Lucide icons at 14, 16, 18 or 20-22px.

### Don't:
- **Don't** signal status with color alone.
- **Don't** add a second accent hue or use semantic colors decoratively.
- **Don't** put shadows on anything but panels, secondary buttons, the submit bar and dialogs.
- **Don't** hide table columns off-screen on phones; use the card layout.
- **Don't** load a webfont or add a dark theme.
