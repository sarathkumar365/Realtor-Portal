# Phase 2 — Loop and architecture

Patterns applied: 2 (evolve architecture), 5 (parallelize carefully), 6 (share context).
State: PROPOSED (defaults accepted by the operator; review before build).

## Decision

A deterministic job pipeline inside the Realtor Portal agentic system, with a model called
at exactly three points. The orchestrator is code, not a model. No router, no coordinator:
there is one capability.

## The loop

```
UI upload ──► RECEIVED
               │ code: validate files (input guardrails, SECURITY.md)
               ▼
           EXTRACTING_METADATA ........ model (M1): propose project, builder, short forms,
               │                         city, and document type per file
               ▼
           AWAITING_METADATA_CONFIRM .. human: confirm or edit on the form
               │
               ▼
           UNBRANDING (per document) .. model + sandboxed code (M2): the
               │                         unbrand-builder-docs skill
               ▼
           VERIFYING .................. code: text sweep, word provenance, number integrity,
               │                         PDF metadata strip
               │                         model (M3): visual check of the rendered pages
               ▼
           FILED_PRIVATE .............. code: create folders, upload to Drive, link private
               │
               ▼
           AWAITING_APPROVAL .......... human: approve or reject with a reason
               │            └──► REJECTED ──► re-run with notes (once) or MANUAL
               ▼
           PUBLISHED .................. code: set "anyone with the link can view",
                                        register heading + link in the Realtor Portal,
                                        notify the uploader
```

Any step can move the job to `FAILED` (see OPERATIONS in SECURITY.md).

## Deterministic or model

| Step | Kind | Why |
|---|---|---|
| Validate upload | Code | File type, size, page count, encryption are checkable |
| M1 Extract metadata and classify documents | Model | Unstructured PDF text; output is a schema, confirmed by a human |
| Confirm metadata | Human | A wrong builder name makes the unbrander miss the real branding |
| M2 Unbrand | Model + code | Existing skill: model judges what is branding, `pymupdf` removes it |
| Verify (text, provenance, numbers, metadata) | Code | All four are exact comparisons; no judgement needed |
| M3 Visual check | Model | Logos, monograms and QR codes are only visible in the render |
| Folder create, upload, share, portal register | Code | Fixed rules from configuration |
| Approve | Human | Last gate before public exposure |

## Structure

- **Per document, a fresh model context.** Each document in a job is unbranded in its own
  context (a subagent, in Claude Code terms). Documents in one job are independent once the
  metadata is confirmed, and a fresh context avoids rot across a 40-page site plan plus three
  floor plans (pattern 7). The shared facts every document needs — project, builder, short
  forms, hit list — are passed explicitly (pattern 6).
- **Sequential, not parallel.** At 5 to 10 documents per day, parallel runs buy nothing and
  make the logs harder to read. Process documents in a job one after another.
- **Intake is an adapter.** The pipeline starts at `RECEIVED` with a job record. The UI
  upload is the v1 adapter; a WhatsApp listener is a later adapter that creates the same
  record. Nothing after `RECEIVED` knows the source.

## Job record

```
job_id, created_at, uploader, source ("ui" | "whatsapp" later)
metadata: project, builder, short_forms[], city, province (default "Ontario"),
          extracted_by_model (copy of M1 output), confirmed_by, confirmed_at
documents[]: source_file_id, sha256, doc_type (price_list | floor_plan | site_plan |
             feature_sheet | other), status, output_file_id, pages_dropped[],
             removed_items[], flags[], verify_results
drive: project_folder_id, share_link
portal: row_ref
approval: approved_by, approved_at | rejected_by, reason_tag, notes
audit[]: every action (see OPERATIONS)
```

## Drive filing rule (from configuration)

```
<UNBRANDED_ROOT>/<province>/<city>/<project> - <builder>/
    <price list>                     at the project folder root
    Floor Plans/<floor plans>        when there is more than one floor plan
    <single floor plan>              at the root when there is only one
    <site plan, feature sheet>       at the root (PROPOSED; confirm with the team)
```

Folder names, the root folder ID and the province list are configuration.

## Rejected

- A model as orchestrator (an agent that "decides" to upload, share, publish). The order
  never changes; a model there only adds nondeterminism and an injection path.
- Parallel per-document subagents. No speed need at this volume.
- A separate Unbrander agent outside the portal. The portal already owns Drive access and
  the sheet; a second system would duplicate both.

## Open questions

1. Where site plans and feature sheets go in Drive (default above).
2. Whether a job may contain documents for more than one project (default: no, one job = one
   project).
