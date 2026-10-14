# Unbrander — model check (U2 step 3)

Date: 2026-10-08. Sample: `townhome-brochure-2.pdf`, 24 pages, builder Arista Homes,
project SouthCal. It is the only real sample so far; a price list and a site plan are
still owed by the team (PHASES.md, U0).

## Result

The pipeline passes on this sample with the chosen models:

| Role | Model | Thinking |
|---|---|---|
| Sort | `google/gemini-2.5-flash` | model default |
| Pick | `google/gemini-3.8-flash` | low |
| Judge | `google/gemini-3.8-flash` | low |
| Repair | `google/gemini-3.8-flash` | low |

That run:
- kept the same 13 pages a person kept with the skill (8–12, 15–22);
- removed the SC monogram and the ARISTA logo from every kept page, and nothing else;
- lost no word, shape or image (no damage finding);
- left no builder name in the text, the raw objects or OCR;
- gave an empty judge list, in one round;
- cost **$0.069** and took **115 s** (sort $0.004, pick $0.042, judge $0.023).

Run 6, the old one-plan design on Gemini 2.5 Pro, cost $0.19, took 681 s, kept 23 pages,
removed brand panels and left black boxes.

## Answer key

The numbered elements on each kept page that are the builder's, read off the numbered
renders: the SC monogram and the ARISTA logo on elevation pages (8, 15, 16), the ARISTA
logo on floor-plan pages. Everything else on the list must stay: the "20' TOWNS" badge,
the teal band, elevation photos and their dashed outlines, basement plans, the "optional
4 bedroom" box. 16 elements in all. The scorer is `.local/unbrand/bakeoff/score.py`.

## Runs

Sort on Gemini 2.5 Flash in every run. It kept exactly the expected 13 pages every time.

| Pick and repair | Judge | Right | Wrong elements | Boxes | Damage | Judge findings | $ | s |
|---|---|---|---|---|---|---|---|---|
| 2.5 Flash, default thinking | 2.5 Flash | 16/16 | 3 | 6 | 1 block, 2 flag | 0 | 0.044 | 157 |
| 2.5 Flash, thinking off | 2.5 Flash | 16/16 | 2 | 4 | 1 block, 1 flag | 1 | 0.047 | 348 |
| Haiku 5.5, default | 2.5 Flash | 16/16 | 0 | 13 | 7 flag | 1 | 0.044 | 222 |
| Haiku 5.5, medium | 2.5 Flash | 16/16 | 0 | 8 | 6 flag | 1 | 0.025 | 136 |
| 3.8 Flash, off | 2.5 Flash | 16/16 | 0 | 0 | 0 | 2 | 0.127 | 157 |
| 3.8 Flash, low | 2.5 Flash | 16/16 | 0 | 0 | 0 | 1 | 0.048 | 105 |
| 3.8 Flash, low | 3.1 Flash-Lite | 16/16 | 0 | 5 | 4 flag | 5 | 0.095 | 239 |
| 3.8 Flash, low | Haiku 5.5 | 16/16 | 0 | 5 | 3 flag | 1 | 0.099 | 262 |
| **3.8 Flash, low** | **3.8 Flash, low** | **16/16** | **0** | **0** | **0** | **0** | **0.069** | **115** |

The first row is run 7, made before pick and repair lost `redact_terms`.

Qwen 3.6 Flash could not be scored: its provider rejected the first pick call with a 400
("Provider returned error"). Not investigated further.

## What the runs showed

- **Every model found every logo** once the elements were numbered. The differences were all
  in what else they removed.
- **Gemini 2.5 Flash broke the "stays" rules.** It removed the teal band and the "20' TOWNS"
  badge, once while its own reason said "not branding", and boxed out model names.
- **Haiku 5.5 picked perfectly but misused boxes.** It read the tiny vertical "ARTIST'S
  CONCEPT" caption on elevation photos as "ARISTA SOUTHCAL" and boxed it out on most plan
  pages. It also boxed out model names on signs in the photos.
- **A wrong judge does harm through the repair.** Weak judges called model names ("THE
  BRADBURY", "The Carson") and an elevation letter branding, and the repair then boxed them
  out. The damage check flagged every case; nothing it missed was found.
- **Thinking helped Gemini 3.8 Flash** (two false judge alarms with thinking off, none with
  low) and cost less, because it needed no repair round.

## Open

- **Boxes are where every remaining mistake came from.** Since 2026-10-08 a guard refuses a
  box or an element whose area holds text that is not the builder's; it would have stopped
  every wrong removal in these runs except the text-free teal band.
- **One sample.** The choice holds for this brochure. Re-run on the price list and the site
  plan when they arrive. Site plans may list hundreds of elements.
- **The golden set** (PHASES.md, U2 step 4) confirms or changes these choices.
