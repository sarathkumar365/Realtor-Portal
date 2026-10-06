# Phases 6 and 7 — Failure modes, metrics and evals

Patterns applied: 10 to 17.
State: PROPOSED.

## Failure modes, by cause

| ID | Failure | Cause |
|---|---|---|
| F1 | Branding left in (name, logo, monogram, QR, URL, phone) | Hit list incomplete (variant spelling, initials); graphic not spotted on the render |
| F2 | Content damaged (plan clipped, label or dimension lost, overlapping text) | Redaction rectangle too large; wrong redaction flags; bad sentence repair |
| F3 | Words added that are not in the source | Model "helpfully" repairs or normalises text |
| F4 | Wrong metadata (project, builder, city) | Extraction error; staff confirm without reading |
| F5 | Wrong document type → wrong folder | Ambiguous document (combined price list and floor plan) |
| F6 | Legal disclaimer removed | Treated as builder boilerplate |
| F7 | Page wrongly dropped or wrongly kept | Triage judgement |
| F8 | Branding in PDF metadata or links | File properties, XMP, hyperlinks not stripped |
| F9 | Update overwrites a live project | Existing folder not detected |
| F10 | Pipeline failure (Drive API, sandbox, portal) | Infrastructure |

## Metrics

**North star: published branding leaks** — number of published documents later found to
carry builder or project identity. Target: 0. This is the costliest wrong action: it is
public and it is the whole point of the product.

| Kind | Metric | Target |
|---|---|---|
| Accuracy | First-pass approval rate | Baseline in first 2 weeks, then rising |
| Accuracy | Rejects by reason tag (F1 to F9) | Tracked weekly |
| Integrity | Changed numbers in approved documents | 0 |
| Outcome | Median time, upload to published | Below today's manual time (measure today's first) |
| Outcome | Staff minutes per document | Below today's (measure today's first) |
| Operations | Jobs in `FAILED` or `MANUAL` per week | Tracked |

## Cross-reference

| Failure | Moves the north star | Moves other metrics | Caught by |
|---|---|---|---|
| F1 | Yes | Reject rate | Text sweep, M3, approver |
| F8 | Yes | — | Metadata strip check |
| F4 | Yes (wrong builder → wrong hit list) | Reject rate | Human confirm with evidence |
| F2, F3 | No | Reject rate, integrity | Provenance and number checks, M3 |
| F6 | No (legal risk instead) | — | Flag to approver |
| F5, F7, F9 | No | Reject rate | Approver, existing-folder rule |
| F10 | No | Time to publish | Operations alerts |

Work F1, F8 and F4 first.

## Golden dataset

- **Source:** real builder PDFs, labelled by Sudhanshu's team reviewing the agent's output
  once from written instructions (pass or fail, what leaked, what was damaged). Where a
  builder original and a staff-made unbranded version already exist (linked from an
  `UNBRANDED` cell), that pair is used as a ready-made label. Revised 2026-10-06: the admin
  team keeps no such tree in Drive, so pairs cannot be assumed.
- **Size to start:** 30 documents — at least 8 price lists, 8 floor plans, 6 site plans,
  6 feature sheets, chosen across different builders.
- **Per case:** original PDF, metadata, hit list, expected kept pages, expected dropped
  pages, and a note of any known hard element (monogram, QR, brand panel).
- **Labeller:** Sudhanshu's team. In U2 they review outputs as files (before and after
  PDFs) with a written checklist; from U4 the approval screen is the labelling UI.

## Eval run

| Check | Kind | Pass rule |
|---|---|---|
| Leak | Code (text sweep + metadata sweep) | Zero hits, every case |
| Number integrity | Code | Zero changed or invented numbers, every case |
| Word provenance | Code | Zero added words, every case |
| Visual branding | LLM judge (M3 prompt) | `branding_visible = no` on every page |
| Plan intact | LLM judge | `plan_intact = yes` on every plan page |
| Page triage | Code against labels | Dropped pages match expected |

**Gate:** any change to the skill, a prompt, the model, or the verify code runs the full
suite. No release if a leak, integrity or provenance case fails, or the judge pass rate falls.

## Production to test cases

- Every reject becomes a new case, tagged with its reason, after the fixed output is approved.
- Every leak reported after publish becomes a case and blocks release until it passes.
- At 5 to 10 documents per day every output is already human-reviewed at approval, so no
  sampling is needed. Revisit if auto-publish is adopted.
- Every month, check the LLM judge against the approvers' decisions; disagreement over 10%
  means the judge prompt needs work.

## Open questions

1. Today's manual time per document and per step (needed for the outcome baselines).
