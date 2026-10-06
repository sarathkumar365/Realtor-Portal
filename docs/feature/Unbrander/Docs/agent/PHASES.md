# Unbrander — build phases

Cut 2026-10-06 from decisions D1–D17 ([INDEX.md](INDEX.md)). Each phase ends in something
that can be shown working. Do not start a phase before the one it depends on is done.

| Phase | Name | Depends on | Who |
|---|---|---|---|
| U0 | Prerequisites | — | Admin team + operator |
| U1 | Spike: tools + models on real PDFs | U0 (sample PDFs, model key) | Engineering |
| U2 | PDF tools, verify, golden set | U1 | Engineering + Sudhanshu's team (labels) |
| U3 | Pipeline to `FILED_PRIVATE` (dry run) | U2, U0 (Google access) | Engineering |
| U4 | Admin app | U3 | Engineering |
| U5 | Approve, publish, undo | U4 | Engineering |
| U6 | Metadata extraction (M1) | U5 | Engineering |
| U7 | Hardening and go-live | U6 | Engineering + operator |
| U8 | Agent loop migration to LangChain / LangGraph | U7 | Engineering |

U1 is a decision gate: if the tools or the models cannot produce a clean document, the
design changes before U2 starts.

---

## U0 — Prerequisites

Nothing here is code. Most of it is done by the Workspace admin.

- Create a Shared Drive for Unbranded. Move **one** project folder into it first and check
  that its existing link (in its `UNBRANDED` cell) still opens. Then move the rest of the
  tree.
- Create a Google Cloud project; enable the Drive API and the Sheets API.
- Create a service account and a JSON key. Add it to the Shared Drive as Content manager.
  Share the sheet with it as Editor. No domain-wide delegation.
- Create a test folder inside the Shared Drive for dry runs (`drive.test_root_folder_id`).
- Pick 3 real builder PDFs for the spike: one price list, one floor plan set, one site plan.
- Confirm the branded originals exist next to the unbranded outputs (for the golden set).
- Measure today's manual time per document (the outcome baseline in EVALUATION.md).

**Done when:** a short script using the service account key can list the Unbranded root and
read the sheet's `UNBRANDED` column; the moved test folder's old link still opens.

## U1 — Spike: tools and models on real PDFs

Run locally, outside the service. Throwaway code, kept in `aura-chat/spikes/unbrander/`.

- First cut of the M2 tools (LOOP.md) on `pymupdf`: `render_page`, `get_text`,
  `redact_terms`, `redact_rect`, `delete_image`, `drop_page`, `add_mark`, `verify`.
  `replace_line` and `rebuild_price_list` only if a sample needs them.
- A minimal tool-calling loop (PydanticAI, as in `agent_pydantic.py`) with the M2 prompt
  adapted from the `unbrand-builder-docs` skill.
- Run the 3 PDFs against 2–3 vision + tool-calling models through OpenRouter (for example
  Gemini Flash, a Claude Sonnet, a GPT model).

**Done when:** for each model, the 3 outputs are reviewed by Sudhanshu's team against what
they produce today, and the following are written into a spike note: leaks found, damage
found, tool calls, wall time and cost per document, and which tools were missing or
unused. Outcome: a model shortlist and a confirmed tool list.

## U2 — PDF tools, verify, golden set

Production code in Aura Chat. New dependencies `pymupdf` and `reportlab` (D8).

- PDF tools as a plain module with their guards (LOOP.md): no word outside the source, no
  changed number, no near-full-page rect, render budget.
- `verify()`: text sweep, word provenance, number integrity, metadata strip (AUTONOMY.md).
- Unit tests on small fixture PDFs checked into `tests/` — no network.
- Golden set: 30 documents from the existing branded/unbranded pairs (EVALUATION.md),
  stored outside git.
- Eval runner: code checks on every case; M3 visual judge per page. How the judge is graded
  is decided at the start of this phase (INDEX.md open question 8).

**Done when:** `pytest -q` is green, and the eval runner passes leak, integrity and
provenance on every golden case with the chosen model.

## U3 — Pipeline to `FILED_PRIVATE` (dry run)

- `jobs` table and the job record (LOOP.md) — schema change, reviewed before it is applied.
- `JobStore` port with its Postgres adapter and a fake in `tests/fakes.py`.
- Worker inside the Aura Chat service: claims with `FOR UPDATE SKIP LOCKED`, one job at a
  time, runs the states `RECEIVED` → `UNBRANDING` → `VERIFYING` → `FILED_PRIVATE`.
- Files on the Railway volume (D12): uploads, working copies, before and after renders.
- `GoogleWriter` port with its adapter: create folders, upload, keep private. Dry-run mode
  writes only under the test root.
- Admin-only API: create a job (upload + metadata typed by hand), get a job, list jobs.
- Input guardrails, budgets, audit log, `unbrander.enabled` switch (SECURITY.md).

**Done when:** an upload by `curl` with an admin token produces a job that reaches
`FILED_PRIVATE`, with the files in the test folder of the Shared Drive and every action in
the audit log.

## U4 — Admin app

Vite + React + TypeScript, its own Railway service (D14).

- Sign-in through Aura Chat's `/login`; admin role only.
- Screens: upload with the metadata form; job list (with stale jobs marked); job detail
  with before and after page images, flags on the pages they concern, dropped pages and
  removed items listed.
- Aura Chat adds the new app's origin to `ALLOWED_ORIGINS`.

**Done when:** an admin uploads a PDF in the app and reviews the resulting `FILED_PRIVATE`
job without using `curl`.

## U5 — Approve, publish, undo

- Approve and reject (with reason tag and notes); one re-run with notes; second reject goes
  to `MANUAL` (AUTONOMY.md).
- Publish in one action: set "anyone with the link can view", write the link to the
  project's `UNBRANDED` cell (D4), notify the uploader.
- Project not in the sheet: the app asks the admin what to do (D13).
- `UNBRANDED` cell already filled: held for a human as an update (AUTONOMY.md).
- Undo publish (SECURITY.md).

**Done when:** one real project goes from upload to a live `UNBRANDED` link in the real
Shared Drive, approved by staff; undo restores the previous state.

## U6 — Metadata extraction (M1)

- M1 call: project, builder, short forms, city, document type per file, each with
  confidence and evidence (CONTEXT.md).
- The upload form is pre-filled; staff entries win; disagreements are flagged.

**Done when:** on the golden set, M1's proposals match the labels, and staff confirm a job
without retyping.

## U7 — Hardening and go-live

- Alerts (failed job, daily cap, eval gate failed), stale-job display.
- Docs: `api.md`, `operations.md` (service account key rotation, volume, worker), and
  `schema.md` for the `jobs` table.
- Deploy both services; run a week with every publish approved; track the metrics in
  EVALUATION.md.

**Done when:** a week of real use with zero published leaks, and the outcome metrics
measured against the U0 baseline.

## U8 — Agent loop migration to LangChain / LangGraph

Decided 2026-10-06; runs after Unbrander is live, so the migration has a working system and
a golden set to be measured against.

- Decide at the start: LangChain v1 (`create_agent`, which runs on LangGraph) or LangGraph
  directly. New dependency — approve before adding.
- Chat agent: a new `AgentRuntime` adapter replaces `agent_pydantic.py`. The port, `tools.py`,
  domain and the SSE contract the PWA reads stay unchanged.
- Unbrander: M1, M2 and M3 move to the same framework. The pipeline, the job states and the
  Postgres queue stay as they are; only the model calls inside a step change.
- Remove PydanticAI once nothing imports it.

**Done when:** `pytest -q` is green; the 50-question chat benchmark scores at least what it
scored before; the Unbrander eval suite passes with zero leaks; latency and cost per answer
are no worse than before, or the difference is accepted.
