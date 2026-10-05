# Handoff: Aura Key — App Icon + Login Screen

## Overview
Two deliverables for **Aura Key**, the internal mobile app of Aura Key Realty (a Greater-Toronto-Area brokerage, ~15 realtor users):

1. **App icon set** — the brand's gold roofline "AK" monogram on a dark ink ground, exported at every size iOS/Android/PWA need.
2. **Login screen** — a single, non-scrolling mobile sign-in screen (Portal ID + Password), on a brand-graded Toronto skyline photograph.

The app is a realtor's daily toolkit (new-build project lists by city, builder/concierge contacts, school rankings, carrying-cost calculator, team leaderboard, own deals). It sits on home screens next to MLS and CRM apps, so it must read as a serious professional tool, not a consumer listing app.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behaviour, **not production code to copy directly**. The task is to **recreate these designs in the target codebase's existing environment** (React Native, Flutter, Swift/Kotlin, or a React/Next PWA) using its established patterns, component library, and theming. If no environment exists yet, pick the most appropriate framework for the project and implement there.

The PNG/SVG icon files, by contrast, **are** production assets — ship them as-is.

## Fidelity
**High-fidelity.** Final colours, typography, spacing, and interaction states. Recreate the UI pixel-accurately using the codebase's own primitives. Exact values are listed under *Design Tokens* below.

---

## Deliverable 1 — App icon

### Artwork
The brand's own mark: an "AK" monogram where the A is drawn as a roofline (peaked, asymmetric — a thin left stroke and a heavy right slab) with a 2×2 gable window punched into it, and a geometric K. Gold metallic gradient on a near-black ink ground with a faint radial vignette.

- Mark occupies **70%** of canvas width, optically centred (well inside the 80% safe zone).
- Maskable variant scales the mark to **60%** so it survives Android's circular crop (a 410px circle on a 512px canvas).
- Ground extends fully edge-to-edge. **No** pre-rounded corners, **no** transparency, **no** drop shadow — iOS and Android apply their own masks.
- sRGB, opaque.

### Colour
| Role | Value |
| --- | --- |
| Ground base | `#0E1A22` |
| Ground vignette centre | `#15262F` |
| Ground vignette edge | `#0A1218` |
| Gold gradient (135°) | `#EDD59B` → `#CDA95B` @45% → `#8A6D33` |

Background gradient: radial, centre 50%/44%, radius 76%.

### Files (in `icons/`)
| File | Size | Used by |
| --- | --- | --- |
| `icon-1024.png` | 1024×1024 | Master / future App Store |
| `apple-touch-icon.png` | 180×180 | iOS home screen |
| `icon-512.png` | 512×512 | Android install prompt, splash, manifest |
| `icon-192.png` | 192×192 | Android home screen, manifest |
| `icon-512-maskable.png` | 512×512 | Android adaptive icon (`purpose: "maskable"`) |
| `icon-master.svg` | vector | Source artwork — regenerate any size from this |
| `favicon.svg` | vector | Browser tab pre-install |
| `preview-blue-1024.png` | 1024×1024 | Alternate: same mark on brand blue `#1F4E6B` (not currently the chosen direction) |

### Web manifest entries
```json
{
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "theme_color": "#0E1A22",
  "background_color": "#0E1A22"
}
```
Plus `<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">` and `<link rel="icon" href="/icons/favicon.svg" type="image/svg+xml">`.

### Monogram path (for in-app use)
The same mark is drawn inline in the login screen as SVG. Reuse it anywhere the logo is needed:

- `viewBox="70 30 905 640"`
- Single `<path>`, `fill` = a linear gradient `#F0DCA9 → #D3AE60 @45% → #9A7A3B` (x1 0, y1 0, x2 1, y2 1)
- Path data:
```
M270 95L150 660L70 660ZM300 50L555 660L445 660L262 118ZM244 428L280 428L280 464L244 464ZM292 428L328 428L328 464L292 464ZM244 476L280 476L280 512L244 512ZM292 476L328 476L328 512L292 512ZM600 40L710 40L710 660L600 660ZM710 250L880 40L965 40L710 375ZM710 455L782 278L975 660L860 660Z
```
Fill rule: **nonzero** (the sub-paths are wound so overlaps stay solid).

---

## Deliverable 2 — Login screen

### Purpose
A realtor signs in with a brokerage-issued **Portal ID** and password. There is no self-serve signup, no password reset, and no social login — accounts are provisioned by an admin.

### Hard constraint
**The entire screen must fit one mobile viewport with no scrolling.** Verified at 402×874 (iPhone 15-class): content height equals viewport height exactly, logo clears the Dynamic Island, footer clears the home indicator.

### Layout
Root: full-height, `overflow: hidden`, `position: relative`.

1. **Background image** — `assets/skyline-dusk.jpg`, absolutely positioned, `object-fit: cover`, `object-position: 52% 30%`.
2. **Scrim** — absolutely positioned over the image:
   `linear-gradient(180deg, rgba(9,19,26,0.58) 0%, rgba(9,19,26,0.30) 18%, rgba(9,19,26,0.34) 34%, rgba(9,19,26,0.52) 62%, rgba(9,19,26,0.84) 100%)`
3. **Content column** — `position: relative`, `height: 100%`, `display: flex`, `flex-direction: column`, `justify-content: space-between`, `padding: 58px 16px 46px`, `box-sizing: border-box`. The 58px top clears the status bar + Dynamic Island; the 46px bottom clears the home indicator. Three children, each `flex-shrink: 0`:
   - brand block
   - login card
   - footer block

Because the column is `space-between` with fixed-height children, it adapts to taller/shorter devices by redistributing the two gaps rather than overflowing. On very short devices (< ~700pt) the trust strip is the first thing to drop.

### Component: Brand block (top, centred)
| Element | Spec |
| --- | --- |
| Monogram SVG | 74×52, gold gradient (above) |
| "AURA KEY" | 21px / 600 / letter-spacing 0.3em (with matching `text-indent` so it stays optically centred) / `#FFFFFF` / text-shadow `0 2px 10px rgba(9,19,26,0.6)`; margin-top 8 |
| Rule + "REALTY" row | margin-top 5; flex, gap 9; two 30×1px rules `rgba(211,174,96,0.85)`; label 10px / letter-spacing 0.4em / `#E0C387` |
| "Welcome back" | margin-top 18; 27px / 700 / letter-spacing −0.01em / `#FFFFFF` / text-shadow `0 2px 14px rgba(9,19,26,0.65)` |
| Sub-copy | margin-top 5; 14px / line-height 1.4 / `rgba(233,237,238,0.9)` / max-width 250px. Text: "Sign in to your realtor toolkit." |

### Component: Login card
Container: `border-radius: 22px`, `padding: 15px 15px 13px`, `box-shadow: 0 18px 44px rgba(6,15,21,0.34)`.

Two treatments (a design toggle — pick one for production; **frosted is the chosen default**):

| Token | Frosted glass (default) | Solid white |
| --- | --- | --- |
| card background | `rgba(255,255,255,0.14)` | `#FFFFFF` |
| card backdrop-filter | `blur(24px) saturate(140%)` | none |
| card border | `1px solid rgba(255,255,255,0.26)` | `1px solid rgba(255,255,255,0.9)` |
| label / input text | `#FFFFFF` | `#17364B` |
| field background | `rgba(9,19,26,0.26)` | `#FFFFFF` |
| field border | `1.5px solid rgba(255,255,255,0.28)` | `1.5px solid #D4DCE2` |
| leading icon stroke | `#D3AE60` | `#1F4E6B` |
| muted text / eye icon | `rgba(233,237,238,0.7)` | `#5B7284` |

If the platform can't do a real backdrop blur cheaply, ship the **Solid white** treatment rather than faking it.

Card contents, in order:

1. **"PORTAL ID" label** — 12.5px / 700 / letter-spacing 0.04em / uppercase; margin-bottom 6.
2. **Portal ID field** — height 46, `border-radius: 12`, `padding: 0 13`, flex row, gap 10. Leading icon: Lucide `user`, 17×17, stroke-width 2. Input 15px, transparent background, no outline. Placeholder "Enter your portal ID", placeholder colour `#93A6B3`.
3. **"PASSWORD" label** — same as above; margin `11px 0 6px`.
4. **Password field** — same geometry. Leading icon: Lucide `lock`. Trailing button toggles `type` between `password` and `text`; icon swaps Lucide `eye` ⇄ `eye-off`, 17×17. **The button's hit box is 44×44** (`padding: 13px; margin: -13px -9px -13px 0`) — keep this; the visible icon must not grow.
5. **Remember me row** — margin-top 13. A single button: 20×20 box, `border-radius: 6`, 1.5px border; checked = fill + border `#1F4E6B` with a white Lucide `check` (stroke-width 3.6, 12×12); unchecked = transparent fill, `rgba(255,255,255,0.5)` border (frosted) / `#C3CED6` (solid). Label 13.5px / 600, gap 8. Hit box padded to 44 tall (`padding: 12px 8px 12px 0; margin: -12px 0`). **Defaults to checked.**
6. **Sign in button** — margin-top 14, full width, height 50, `border-radius: 13`, background `#1F4E6B`, label 16.5px / 700 `#FFFFFF`, `box-shadow: 0 8px 18px rgba(31,78,107,0.32)`. Hover `#26597A`; active `#163A50` with the shadow removed.
7. **Support line** — margin-top 13, centred, 12px / 500, muted colour. Text: "Need access? Contact your admin for support." Plain text, **not** a link.

There is deliberately **no** "Forgot password?", no signup link, and no phone/email support row.

### Component: Footer block
- **Trust strip** — one row, `justify-content: space-between`, `padding: 0 4px`. Three items, each an icon + label in a flex row with gap 6. Icons are Lucide, 14×14, stroke `#D3AE60`, stroke-width 2: `shield-check` / a small line-chart / `users`. Labels 11px / 600 / `rgba(233,237,238,0.9)`, `white-space: nowrap`, text-shadow `0 1px 6px rgba(9,19,26,0.8)`. Copy: **Secure** · **Built for realtors** · **Team first**.
- **Copyright** — margin-top 10, centred, 10.5px, `rgba(233,237,238,0.55)`. Text: "© 2026 Aura Key Realty".

---

## Interactions & Behavior

| Interaction | Behaviour |
| --- | --- |
| Password eye toggle | Flips input type `password` ⇄ `text`; icon swaps `eye` ⇄ `eye-off`. Local UI state only. |
| Remember me | Toggles a boolean; drives the checkbox fill/border. Default **on**. Should persist the Portal ID (not the password) to secure storage. |
| Sign in | Submits Portal ID + password. Not wired in the prototype. |
| Focus | Inputs suppress the browser default outline in the mock; **in production give every field a visible focus ring** (2px, `#D3AE60` on the frosted card / `#1F4E6B` on solid) — do not ship without one. |

### States to build (not in the prototype — design them from these tokens)
- **Loading** — Sign in button shows a spinner, label hidden, button disabled at 45% opacity, fields disabled.
- **Error** — field border → a red from the app's error ramp, error text 12px directly under the offending field; a general auth failure ("Portal ID or password is incorrect") sits above the Sign in button.
- **Validation** — both fields required; validate on submit, not on keystroke. Portal ID trims whitespace.
- **Empty state** — Sign in stays enabled; validation messages carry the feedback.

### Responsive behavior
Portrait phone only. The `space-between` column absorbs height differences. Below ~700pt viewport height, hide the trust strip first (it is already an explicit toggle in the design), then reduce the brand block's top margin. Do not introduce scrolling; do not shrink the 44px hit boxes. Landscape and tablet are out of scope for this screen.

### Accessibility
- Every interactive control has a **≥44×44** hit box (achieved with padding + matching negative margin so the visual layout is unchanged). Preserve this.
- The eye toggle needs an accessible label that reflects state ("Show password" / "Hide password").
- Labels are real `<label>`s bound to their inputs.
- Body copy over the photograph relies on the scrim for contrast — if you swap the image, re-check contrast, especially the 11px trust strip.

## State Management
```
showPassword : boolean   // default false — eye toggle
rememberMe   : boolean   // default true  — persists Portal ID
portalId     : string    // controlled input
password     : string    // controlled input
submitting   : boolean   // to build: drives Sign in loading state
error        : string?   // to build: auth failure message
```
Data: a single `POST` to the auth endpoint with `{ portalId, password }`, returning a session token. No other fetches on this screen.

## Design Tokens

### Colour — brand palette
| Name | Hex |
| --- | --- |
| ink | `#0E1A22` |
| paper | `#E9EDEE` |
| blue | `#1F4E6B` |
| pine | `#0F6349` |
| ochre | `#9A6104` |

### Colour — screen values
| Role | Value |
| --- | --- |
| Primary action | `#1F4E6B` (hover `#26597A`, active `#163A50`) |
| Gold (icon / accent) | `#D3AE60`; light `#E0C387`; gradient `#F0DCA9 → #D3AE60 → #9A7A3B` |
| Text on photo | `#FFFFFF`, secondary `rgba(233,237,238,0.9)`, tertiary `rgba(233,237,238,0.55)` |
| Text on white card | `#17364B`, muted `#5B7284`, placeholder `#93A6B3` |
| Card borders (solid) | `#D4DCE2`, rules `#E2E8ED`, unchecked box `#C3CED6` |
| Scrim base | `rgba(9,19,26,α)` |

### Spacing
Screen padding `58 / 16 / 46`; card padding `15 / 15 / 13`; vertical rhythm inside the card 6 · 11 · 13 · 14; icon-to-text gaps 5–10.

### Typography
System UI stack (`-apple-system, "SF Pro Text", "Segoe UI", sans-serif`) — map to the platform's own default face.

| Use | Size / weight / tracking |
| --- | --- |
| Wordmark | 21 / 600 / 0.3em |
| "REALTY" | 10 / 400 / 0.4em |
| Headline | 27 / 700 / −0.01em |
| Sub-copy | 14 / 400 / lh 1.4 |
| Field labels | 12.5 / 700 / 0.04em, uppercase |
| Input text | 15 / 400 |
| Button | 16.5 / 700 |
| Remember me | 13.5 / 600 |
| Support line | 12 / 500 |
| Trust strip | 11 / 600 |
| Copyright | 10.5 / 400 |

### Radius
Fields 12 · Sign in button 13 · Checkbox 6 · Card 22 · **App icon 0** (the OS masks it).

### Shadow
Card `0 18px 44px rgba(6,15,21,0.34)` · Button `0 8px 18px rgba(31,78,107,0.32)`.

## Assets
| Asset | Source / notes |
| --- | --- |
| `assets/skyline-dusk.jpg` | Toronto sunset skyline (CN Tower, waterfront). **Licensed from Adobe Stock, asset ID 687241424.** The original is warm orange; it has been re-graded into the brand palette (luminance mapped through an ink → steel-blue → gold ramp) and cropped to 900×1400. Confirm the licence covers the app's distribution before shipping, and keep the graded version — an ungraded swap will clash with the palette. |
| `icons/*` | Generated from the brand monogram — original vector artwork, no third-party licence. |
| Interface icons | **Lucide** (lucide.dev), stroke-width 2. Used: `user`, `lock`, `eye`, `eye-off`, `check`, `shield-check`, `users`, plus a small line-chart glyph. Pull these from Lucide rather than re-tracing the inline copies. |
| Fonts | None bundled — system UI throughout. |

## Files
| File | What it is |
| --- | --- |
| `Aura Key Login.dc.html` | The login screen prototype (open in a browser). It renders inside an iPhone frame for presentation — `ios-frame.jsx` is **presentation chrome only**, not part of the design. |
| `Aura Key Icon.dc.html` | The icon spec sheet: master artwork, legibility at 180/120/60/48px, iOS + Android mask previews, home-screen comparison, file table. |
| `ios-frame.jsx` | Device bezel used by the login prototype. Do not port. |
| `icons/` | Production icon assets — ship these as-is. |
| `assets/skyline-dusk.jpg` | Production background image. |

### Reading the prototypes
Both HTML files are single-file components: markup at the top, a small logic class at the bottom holding state and the derived colour values. Colour tokens that differ between the frosted and solid card treatments are computed in that class — read it alongside the markup when tracing where a value comes from. Open either file directly in a browser; no build step, no server.
