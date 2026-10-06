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
| Text sweep (hit list + generic terms) | Zero hits | One targeted retry, then flag |
| Word provenance | Every output word exists in the source, except the Aura Key mark | Flag; never auto-fix |
| Number integrity | Every number in the output exists in the source | Block the document |
| PDF metadata strip | Title, author, subject, keywords, producer, XMP, links, annotations, embedded files cleared | Retry, then block |
| Visual check (M3) | "No branding visible" and "plans intact" on every page | Fail or unsure → flag for the approver |

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
| M2 tool calls per document | ~15 (from the skill; recalibrate after the spike) | Stop, report what is resisting |
| Render passes per document | 2, plus a third for failed pages only | Stop |
| Wall time per document | 10 minutes (PROPOSED) | `FAILED`, notify |
| Retries | 1 targeted retry per failed check | Flag or block |
| Documents per day | 30 (3× current volume) | Queue holds; alert the operator |
| Model cost per document | Open — set after first measured runs | Alert |

## Open questions

1. Model cost ceiling per document (measure first).
2. Who is allowed to approve (default: any admin, the same role that uploads; a second
   person is not required at this volume).
