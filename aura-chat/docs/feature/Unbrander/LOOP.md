# Phase 2 — Loop and architecture

Patterns applied: 2 (evolve architecture), 5 (parallelize carefully), 6 (share context).
State: PROPOSED (defaults accepted by the operator; review before build).
![alt text](image.png)

## Decision

A deterministic job pipeline inside Aura Chat (`aura-chat/`), with a model called at exactly
three points. The orchestrator is code, not a model. No router, no coordinator: there is one
capability.

Aura Chat becomes write-capable with this feature (decision D1, 2026-10-05). The chat agent
stays read-only; writes happen only in this pipeline, only by code, and the public ones only
after a human approves.

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
           UNBRANDING (per document) .. M2: sort, pick, judge, repair (below);
               │                         the tools are our code, run in Aura Chat
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
                                        write the link into the UNBRANDED cell,
                                        notify the uploader
```

Any step can move the job to `FAILED` (see OPERATIONS in SECURITY.md).

## Deterministic or model

| Step                                          | Kind         | Why                                                                                   |
| --------------------------------------------- | ------------ | ------------------------------------------------------------------------------------- |
| Validate upload                               | Code         | File type, size, page count, encryption are checkable                                 |
| M1 Extract metadata and classify documents    | Model        | Unstructured PDF text; output is a schema, confirmed by a human                       |
| Confirm metadata                              | Human        | A wrong builder name makes the unbrander miss the real branding                       |
| M2 Unbrand                                    | Model + code | Model judges what is branding and calls a named tool; the tool (`pymupdf`) removes it |
| Verify (text, provenance, numbers, metadata)  | Code         | All four are exact comparisons; no judgement needed                                   |
| M3 Visual check                               | Model        | Logos, monograms and QR codes are only visible in the render                          |
| Folder create, upload, share, portal register | Code         | Fixed rules from configuration                                                        |
| Approve                                       | Human        | Last gate before public exposure                                                      |

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
- **Queue is Postgres** (decision D6). Job records live in a `jobs` table in the existing
  Railway Postgres. A worker claims the next job with `SELECT … FOR UPDATE SKIP LOCKED`. No
  new service. At 5 to 10 documents a day one worker is enough.

## M2: sort, pick, execute, judge, repair (decision D23, revised 2026-10-08)

```
1 SORT      one call, every page's text and render ─► per page: kind, keep or drop, why;
            the names and contact details to take out of the text
2 PICK      one call per kept page: the render with code-found elements numbered on it
            ─► the element numbers that are branding (a box only as a last resort)
3 EXECUTE   code applies the actions through the tool guards (no model)
4 CHECK     verify() (code), including the damage check
5 JUDGE     one call per kept page (after round 1, per repaired page only): the output
            render, the source's remaining elements numbered on it ─► what is
            still visible, by element number
6 REPAIR    one call per failing page: problems + numbered render ─► more actions
            back to 3, at most unbrander_max_rounds (2) repairs
```

Built in `app/capabilities/unbrander/unbrand.py`, with the model calls behind the
`UnbrandModels` port.

- **No model is asked where anything is.** Code lists each page's elements (every image
  placement, and every group of vector shapes within 6 points of each other, black and gray
  apart from coloured: black groups up to 5% of the page, coloured up to half, leaving out a
  page-sized background) and draws their numbers on the render. A model answers with numbers; code
  removes the element by its own outline. This is set-of-mark prompting (Microsoft, 2023).
  It replaced freehand boxes after run 6: Gemini Flash answered boxes as
  `[ymin, xmin, ymax, xmax]` whatever order was asked, Pro's boxes drifted when it saw 24
  pages at once, small marks were missed by their own width, and loose boxes meant removing
  every shape a box touched, which took whole brand panels.
- **The sort drops what a buyer does not need.** Floor plans, elevations, site plans, price
  lists, feature sheets and terms stay; covers, about-the-builder, community, award and
  portfolio pages go. The skill's own output of the spike brochure kept the 13 elevation and
  plan pages of 24 and lost no word; run 6 kept 23, cut into the cover, award and portfolio
  pages, and took the "20'" badge text off ten floor plans. Code ignores a
  drop of a kind buyers need, and `drop_page` refuses a page with a room dimension or a
  price, whatever the model says.
- **Code adds every phone number and email on a kept page** to the sort's terms, as the
  skill's hit list did. The sort missed both on the Bright Side price list.
- **Only the sort names text to remove.** Pick and repair see one page and can remove
  elements or, as a last resort, a box; they cannot add `redact_terms`. In run 7 a repair
  added "The Carson", a model name, and took it off every page.
- **The mark position is code:** bottom right when a plan or elevation stays, bottom centre
  otherwise (the skill's table).
- **Per-page calls run four at a time**; answers are put back in page order, so a round is
  deterministic.
- **Every round replays all actions so far on a fresh copy of the source**, then saves and
  checks. A round is deterministic and safe to repeat, which the U3 worker relies on.
- **Only `retry` findings drive a repair.** A `block` (a changed or lost number, OCR not
  run) is not something a further removal can fix, and goes to a person. A refused drop is
  not a problem: the page simply stays.
- **The judge adds, it never clears.** Judge findings sit beside the verify report for the
  approver; `passed` is the code checks alone. Repair stays a separate role from the judge
  (Sarath, 2026-10-08).
- **A refused action** is recorded with the guard's reason and fed to the next repair.
  A page whose repair actions were all refused, or whose repair proposed nothing, is not
  repaired again: the model proposes the same thing, and its problems go to the approver as they stand.
- **Model tiers are settings** (`unbrander_sort_model`, `_pick_model`, `_judge_model`,
  `_repair_model`, and `unbrander_thinking` per role). The model check of 2026-10-08 chose
  Gemini 2.5 Flash to sort and Gemini 3.8 Flash with low thinking for the rest
  ([model-check.md](model-check.md)); the golden set confirms or changes them (D16).
- **Answers are strict JSON schema output.** The provider constrains generation to the
  schema; function calling only asked, and Gemini Flash answered in prose once and wrote a
  box as a string once. Items are still validated one by one, and a bad one is dropped.
- **An answer with no usable list is asked for once more.** Then: a sort fails the job, a
  pick or repair adds nothing (the judge and the approver still see the page), and a judge
  becomes one `block` finding on that page.
- **redact_terms skips a term it cannot find** and removes the rest; the outcome names the
  skipped term. In run 5 one variant (`ARISTA’s`) cancelled the whole call. Rejected
  instead: removing the hit list in code with no model judgement, because a project name can
  also be a street name that must stay.
- **Output is capped per role** (sort 8k tokens, the per-page roles 2k). Flash as judge once
  repeated one leak until its 65k limit; a capped loop fails fast and is asked again.
- **A broken connection is tried again** (3 tries). The OpenRouter SDK retries only httpx
  network errors, and an unwrapped `ssl.SSLError` ended run 5.
- **Page images are JPEG** (quality 85): a 24-page brochure is 38 MB as PNG, over
  OpenRouter's 30 MB per-request image limit, and 7 MB as JPEG.

## M2 tools (decision D3)

The model does not write code. It sees page renders and text and decides; its plan is a list of these tool calls, which code applies.
Each tool is a plain Python function in Aura Chat built on `pymupdf` (and `reportlab` for
price lists). They carry the logic of the `unbrand-builder-docs` skill; the skill's prose
becomes the M2 system prompt.

| Tool                             | Does                                                                                                                                | Guard inside the tool                                                                      |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `render_page(page)`              | 100 DPI image of one page with its elements numbered on it, plus the list of elements                                               | At most 3 renders of any one page                                                          |
| `get_text(page)`                 | Extracted text, delimited as data                                                                                                   | —                                                                                          |
| `redact_terms(terms[])`          | Removes every whole-word match on every page (text only; plan line art kept)                                                        | Rejects a term not in the source's text layer; logs every removed match                    |
| `remove_element(page, id)`       | Removes one numbered element (a logo, monogram, QR, an image placement) by its own outline                                          | Rejects an unknown number, any element holding text that is not the builder's, and any element over the page's own drawing (a plan's lines would go with it); only shapes wholly inside go |
| `redact_rect(page, box)`         | Last resort: branding with no element, such as a logo printed inside a photo                                                        | Rejects a box over half the page, any box holding text that is not the builder's, any box that cuts through a drawn shape, and any box over the page's own drawing |
| `drop_page(page, reason)`        | Removes a page a buyer does not need                                                                                                | Reason required; refuses a page with a room dimension or a price; the last page stays      |
| `replace_line(page, rect, text)` | Sentence repair after a removal                                                                                                     | Rejects any word not in the source                                                         |
| `add_mark(position)`             | Aura Key mark, same position on every page                                                                                          | `bottom_right` or `bottom_centre`; once per document                                       |
| `rebuild_price_list(rows)`       | House-style price list                                                                                                              | Rejects any number not in the source                                                       |
| `verify()`                       | Text sweep, raw-object sweep, OCR sweep (3 modes), number integrity, provenance, metadata strip, cover-up, page sizes, damage (AUTONOMY.md) | Code only; results stored on the document record                                    |

`delete_image` was removed on 2026-10-08: it emptied an image on every page that drew it,
and the transparent stand-in it leaves turned black when a later area removal blanked part of
it (run 6, page 3). `remove_element` removes one placement on one page.

Built so far (U2 step 1): every row above except `replace_line` and `rebuild_price_list`, in
`tools.py` over the `PdfEditor` port. Conventions:

- **Pages are source numbers** for the whole run. A dropped page is removed, and the mark
  added, only when the document is saved, so a number never shifts under the model and a
  later redaction cannot remove the mark.
- **Boxes are on a 0–1000 grid** over the page, `[x0, y0, x1, y1]`: the grid Gemini emits
  natively, and independent of render DPI.
- A refused call raises `ToolRejected` before anything changes; the loop returns the reason
  to the model as the tool's error.
- **`finish()` is code, not a model tool.** It saves the document, then strips the info
  dict, the XMP (the catalog's and every object's), annotations, links, attachments and layer
  names. Hidden text stays: in a scan it is the OCR layer that keeps prices searchable. It hands `dropped_pages` and the removal log to `verify()` and the
  approver.

There is no tool to run code, read files, or reach the network. Reference for tool shape:
[pdf-redaction-mcp](https://github.com/marc-hanheide/pdf-redaction-mcp) (MIT, inactive),
read for ideas only, not a dependency.

## Who does the writes (decisions D2, D7)

After approval, Aura Chat's own code creates the folders, uploads, sets sharing and writes
the sheet, directly through the Google Drive and Sheets APIs, behind a `GoogleWriter` port.
The model never calls it.

Rejected (2026-10-06): a new Apps Script action. It needed no new credential, but Apps
Script caps a request near 50 MB and a run at 6 minutes, so a large site plan sent as base64
could fail, and every write would need a clasp deploy. The Drive API's resumable upload has
no such limit.

The write is to the project row's existing `UNBRANDED` cell (D4), which the portal already
shows as the "Drive" button. An empty cell means a new project; a filled cell means an
update (AUTONOMY.md).

## UI (decision D9)

A separate admin app, not a PWA screen: the first piece of the Aura Agent UI. Three screens
for this feature — upload with the metadata form, job list, approval with before and after
page images. It signs in through Aura Chat's `/login` and is shown to the admin role only.
Stack: Vite + React + TypeScript, deployed as its own Railway service (D14).

## Job record

```
job_id, created_at, uploader, source ("ui" | "whatsapp" later)
instructions (the operator's request, free text; steers M2, never overrides a guard)
metadata: project, builder, short_forms[], city, province (default "Ontario"),
          extracted_by_model (copy of M1 output), confirmed_by, confirmed_at
documents[]: source_file_id, sha256, doc_type (price_list | floor_plan | site_plan |
             feature_sheet | other), status, output_file_id, pages_dropped[],
             removed_items[], flags[], verify_results
drive: project_folder_id, share_link
portal: row_ref (project row; link goes in its UNBRANDED cell)
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
- Running the skill as-is through the Claude API code-execution tool. Its sandbox has no
  network and no `pymupdf`, so the skill's `pip install` step fails; and model-written code
  is an injection path from PDF text (checked 2026-10-05 against the API docs).
- Our own code-execution sandbox on Railway. Works, but must be built and secured; named
  tools give the same result with a smaller attack surface.
- LangGraph as the workflow engine (2026-10-07). The flow is linear with two human gates;
  its checkpoints are hard to query, so the `jobs` table would be needed anyway as a second
  source of truth, and the worker, queue and lock are not in open-source LangGraph.
- One agent loop over the whole document, calling a tool per turn (2026-10-07). About ten
  turns that each resend every page; a single plan from the whole document, checked by code,
  needs far fewer calls and gives the approver a plan to read.
- A cheap per-page executor model between plan and execution. It would only re-apply the
  planner's decisions. (2026-10-08: the planner's boxes did prove inaccurate; the answer was
  per-page picking by element number, not an executor.)
- Freehand boxes as the main way to remove drawn branding (2026-10-08). Vision models'
  boxes are approximate (Gemini 2.5 Pro scores about YOLOv3-level on COCO; Claude's docs say
  coordinates are approximate), and every inaccuracy became damage or a leak.
- One plan call for the whole document with every action (2026-10-08). Pro took 236 s and
  $0.17 for it, and its boxes were the least accurate exactly because it saw every page.

## Open questions

1. Where site plans and feature sheets go in Drive (default above).
2. Whether a job may contain documents for more than one project (default: no, one job = one
   project).
3. How a job finds its project row when the project is not in the sheet yet.
