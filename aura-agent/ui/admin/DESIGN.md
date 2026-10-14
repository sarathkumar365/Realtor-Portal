# Aura Agent admin — design language

Read this before building or changing any screen. The mockup of record is
https://claude.ai/artifact/1xviSFsch6WXeuNEHCxbMJ (private to the owner). Where
the mockup and this file disagree, this file wins.

## Stance

A quiet instrument panel for the two or three admins who check the agent's
work. Minimal and modern; it must not look generated. The look is inspired by
the UI of the Entertainer project (monochrome, mono labels, hairlines). The
ideas were borrowed; no code was copied.

## Colour

- Monochrome. Hierarchy comes from brightness and size, never from hue.
- Dark first. A light palette follows `prefers-color-scheme: light`.
- **Gold has one job: it marks what the agent changed and is waiting for you
  to check.** That covers change counts, the "Needs review" state, and page
  ticks in the review viewer. Nothing else is gold: not buttons, not links,
  not focus rings.
- No green, red or blue status colours. A state is a word and a glyph.
- One exception: `danger` red, for error text, invalid fields and destructive
  confirms. Never for a job's state.
- PDF pages are white. On a dark screen they are dimmed until hovered, so a
  wall of them does not shout over the interface (`paper-dim` utility). The review viewer is always
  dark, so the pages are the only light on screen.

| Token | Dark | Light | Use |
|---|---|---|---|
| `void` | `#09090B` | `#FAFAFA` | Page background |
| `raise` | `#0F1013` | `#FFFFFF` | Cards, inputs |
| `raise-2` | `#16171B` | `#F2F2F3` | Active nav item, selected tab |
| `fg` | `#F4F4F5` | `#0B0B0D` | Text, primary button fill |
| `fg-2` | `#A1A1AA` | `#4D4D55` | Secondary text |
| `fg-3` | `#82828B` | `#6C6C74` | Labels, hints, disabled. At least 4.5:1 on every background: labels are 10px, so this is the floor, not a target |
| `line` | white 9% | black 10% | Borders you should notice |
| `line-2` | white 4.5% | black 5.5% | Hairlines, dividers |
| `gold` | `#C9A227` | `#C9A227` | Change markers (fills) |
| `gold-text` | `#D9B648` | `#8C6D0E` | Gold used as text |
| `danger` | `#E5484D` | `#C62F2F` | Errors and destructive confirms only |

## Type

- Geist for text. Geist Mono for labels, numbers and buttons. Both are
  self-hosted, so the CSP needs no font host.
- Three sizes with hard jumps and nothing in between:
  - **label** (`label-caps` utility): mono, 10px, uppercase, 0.18em tracking, `fg-3`
  - **body**: 13.5px, line height 1.55
  - **reading** (`reading` utility): mono, 30px, -0.04em, tabular figures
- Titles: h1 28px, weight 600, -0.035em. h2 17px, weight 600.
- Numbers that line up in a column are always mono with tabular figures.

## Surfaces

- Hairlines, no shadows.
- Card: `raise` background, `line-2` border, radius 10px. On hover the border
  goes to `line`.
- Readings (`Readings` / `Reading`): a grid of cells divided by 1px of `line-2` (the grid gap shows
  the background), not separate cards. Use for summaries, run details and
  organization facts.
- Section (`Section`): hairline top border, title on the left, a count or action on the
  right.
- List: rows split by `line-2`, `raise` background on hover; the whole row is
  one link.

## Controls

- Buttons: radius 4px, mono uppercase 10.5px.
  - primary: solid `fg` with `void` text. One per screen.
  - quiet: outlined with `line`.
  - bare: text only.
- Inputs: `raise` background, `line` border, `fg` border on focus. The field
  label uses the label style above the field; hints sit under it in `fg-3`,
  12px.
- Status (`StatusMark`, see COMPONENTS.md): a glyph and a word, never a coloured pill.
  - Needs review: filled gold dot, gold text
  - Working: spinning ring
  - Filed in Drive: filled `fg-2` dot
  - Failed: hollow square, `fg` text

## Layout

- Collapsible left rail: 216px expanded, 60px collapsed (icons only). It
  collapses automatically under 820px. Nav labels are mono uppercase; the
  active item has a `raise-2` fill.
- Content column: max 1120px, 28px side gutters (16px on a phone), 34px
  between sections.
- Review viewer: full screen. Before | hairline | After, each page fit to the
  height. It never scrolls. Large round arrows at the bottom, ← → and Esc on
  the keyboard, and a tick strip with one tick per page.

## Motion

- One curve, a spring: `cubic-bezier(.16, 1, .3, 1)`.
- Page enter: 6px rise plus fade, 0.5s. Hovers: 0.25–0.4s.
- Respect `prefers-reduced-motion`.

## Copy

- Plain words from the admin's side: "Needs review", "File in Drive",
  "Start unbranding".
- No marketing lines and no reassurance sentences.
- No developer metrics on the surface. Rounds, cost and the event timeline
  live under "Run details".

## Don't

- Coloured pills, gradients, shadows, emoji.
- Rounded everything; centred hero copy.
- More than one accent colour.
- Inter or Space Grotesk.
