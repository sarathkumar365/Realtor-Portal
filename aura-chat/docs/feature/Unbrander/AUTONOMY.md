# Phases 3 and 4 — Autonomy, the human, and the decision rule

Pattern applied: 4 (human-in-the-loop).
State: PROPOSED (defaults accepted by the operator; review before build).

## Per-action autonomy

| Action | Cost if wrong | Cost if missed | Mode |
|---|---|---|---|
| Extract metadata (M1) | Wrong builder → branding left in; wrong city → wrong folder | Staff type it | Human confirms a draft |
| Unbrand (M2) | Branding left, or content damaged | Staff do it manually | Autonomous; checked at approval |
| Drop a page | Buyer information lost | Blank page delivered | Autonomous; every dropped page listed for the approver |
| Remove a disclaimer | Legal disclosure lost | Builder text stays | Never autonomous; flagged for the approver |
| Create folders, upload (private) | Clutter in Drive; reversible | Nothing | Autonomous |
| Make link public | Leaked branding is exposed to every realtor | Delay | Human approves |
| Write link to the `UNBRANDED` cell | Realtors see a bad document | Delay | Human approves (same click as above) |
| Notify uploader | Noise | Uploader checks the UI | Autonomous |

Approving publishes in one action: share and portal registration happen together, so a
public link never exists without a portal entry, or the reverse.

## While the human is away

Jobs wait in `AWAITING_METADATA_CONFIRM` or `AWAITING_APPROVAL`. Nothing is public while
waiting. No timeout auto-approves. A job waiting more than 24 hours is shown as stale in the
UI.

## Earning autonomy

Start with every publish approved. Consider auto-publish for one document type at a time
(price lists first, lowest visual risk) only when all hold:

- 50 consecutive approvals of that type with no reject;
- zero branding leaks found after publish over the same period;
- the eval suite (EVALUATION.md) passes at 100% on leak and integrity checks.

Auto-publish, if adopted, becomes deferred review: published, then reviewed within one
working day.

## Decision rule — verification gate

A document reaches `FILED_PRIVATE` only with all code checks passed. The visual check can
pass, fail or be unsure.

| Check | Pass | Otherwise |
|---|---|---|
| Text sweep (hit list) | Zero hits, whole-word, including spaced and hyphenated variants | One targeted retry, then flag |
| Text sweep (generic: URL, email, phone, domain) | — | Flag; brochures quote legitimate addresses too |
| Raw-object sweep | No hit-list term in any object definition, layer name or metadata stream (each image can carry its own XMP) | One targeted retry, then flag |
| OCR sweep | No hit-list term in the rendered page, in normal, inverted and light-ink modes | One targeted retry, then flag; OCR not run blocks |
| Word provenance | Every output word exists in the source, except the Aura Key mark | Flag; never auto-fix |
| Number integrity | Every number in the output exists in the source | Block the document |
| PDF metadata strip | Title, author, subject, keywords, creator, producer, XMP, links, annotations, embedded files cleared | Retry, then block |
| Cover-up | No opaque shape drawn over 90% or more of earlier text or an image | One targeted retry, then flag |
| Page integrity | Kept pages keep their size; page count matches the declared drops | Flag |
| Damage | No source word on a kept page gone except the builder's names and contact details (URL, email, phone, domain), whichever tool took it; no more than 0.2% of the page's picture changed outside every removal and the mark's strip | A lost word with a digit (a dimension, a price) blocks; other lost words and lost shapes flag |
| Visual check (M3) | The judge reports no branding visible on any page | A finding drives a repair round; what is left after the last round goes to the approver. The judge never clears a code finding |

Flags do not stop the job. They go to the approver, marked on the page they concern. A
blocked document stops the job's publish until a human resolves it.

The "not sure" path is always: flag, show the page, let the human decide.

## Other rules

- **Project folder already exists, or the project's `UNBRANDED` cell is already filled:**
  do not overwrite or merge. Move the job to the approver
  with "update to existing project". The update policy (overwrite or backup) is deferred; until
  decided, a human handles updates.
- **Project not in the sheet:** the admin app shows the job and asks the admin what to do
  (pick a row, or hold until the project is added) (D13).
- **City not in the configured list:** stop at metadata confirmation; the human picks or adds.
- **Reject:** the reason tag and notes are fed into one re-run. A second reject sends the job
  to `MANUAL`.

## Budgets

| Budget | Limit | On breach |
|---|---|---|
| M2 model calls per document | 1 sort + 1 pick per kept page, 1 judge per kept page in the first round and per repaired page after, + 1 repair per failing page (D23) | Rounds stop at the limit; what is left goes to the approver |
| Render passes per document | 2, plus a third for failed pages only: at most 3 renders of any one page, enforced in `render_page` | The call is refused |
| Wall time per document | 10 minutes (PROPOSED) | `FAILED`, notify |
| Model output | sort 8k tokens; pick, judge and repair 2k each | A capped answer does not parse and is asked for once more |
| Broken connection | 3 tries per call, 2 s then 5 s apart (on top of the SDK's own retry of network errors and 5xx) | The error goes up; the run fails as a General error |
| Retries | Up to `unbrander_max_rounds` (2) repair rounds, failing pages only, driven by `retry` findings and the judge; a page whose last repair was refused whole, or proposed nothing, is not repaired again | Flag or block |
| Documents per day | 30 (3× current volume) | Queue holds; alert the operator |
| Model cost per document | Open — set after first measured runs | Alert |

## Open questions

1. Model cost ceiling per document (measure first).
2. Who is allowed to approve (default: any admin, the same role that uploads; a second
   person is not required at this volume).
