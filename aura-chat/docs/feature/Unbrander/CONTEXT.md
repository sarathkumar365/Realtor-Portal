# Phase 5 — Context

Patterns applied: 7 (context failure modes), 8 (compress), 9 (feed errors back).
State: PROPOSED.

Three model calls; each gets only what it needs.

## M1 — Metadata extraction and classification

| In | Out (schema-validated) |
|---|---|
| Upload form fields, if any; file names; extracted text of the first two pages of each file; page count | `project`, `builder`, `short_forms[]`, `city`, per file `doc_type`; each with `confidence` (high / low) and `evidence` (page and the words it came from) |

- No tools. Output that fails the schema is rejected and retried once.
- Form fields entered by staff win over extraction; the model only fills blanks and flags
  disagreements.
- The evidence field lets the human confirm in seconds.

## M2 — Unbrand (per document, fresh context)

| In | Excluded |
|---|---|
| A system prompt adapted from the `unbrand-builder-docs` skill (judgement rules only; its code moves into the tools); the M2 tool definitions (LOOP.md); confirmed metadata; the hit list; the document's extracted text; page renders at 100 DPI, fetched through `render_page`; reject notes on a re-run | Other documents, other jobs, Drive and portal tools, any code-execution tool, credentials, network |

- **Never compressed or dropped:** the confirmed metadata, the hit list, and the skill's
  "every word must come from the source" rule. These stay at full fidelity for the whole run.
- **Errors fed back:** the tool that failed, its error message (for example "word not in
  source: Townhomes"), and the verify result that failed.
  One retry (pattern 9). When the same error recurs across documents, its fix goes into the
  prompt or the tool, not into each run.
- **Rot guard:** documents over 20 pages are rendered and reviewed in batches of 10 pages;
  earlier batches are kept as a one-line result per page, not as images.
- **Untrusted text:** extracted PDF text is wrapped as data with a clear delimiter. The
  model is told it is content to clean, never instructions.

## M3 — Visual check

| In | Out |
|---|---|
| Before and after renders of one page, the hit list | Per page: `branding_visible` (yes / no / unsure), `plan_intact` (yes / no / unsure), `overlap_text` (yes / no), short note |

- Categorical, not scores (pattern 17).
- Separate call from M2, so the model that did the work is not grading itself in the same
  context.

## Open questions

1. Which model for each call (decided in the portal project by cost and latency; M3 needs
   vision).
