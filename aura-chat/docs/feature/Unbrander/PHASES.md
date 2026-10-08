# Unbrander — build phases

Cut 2026-10-06 from decisions D1–D17 ([INDEX.md](INDEX.md)). Each phase ends in something
that can be shown working. Do not start a phase before the one it depends on is done.

| Phase | Name | Depends on | Who |
|---|---|---|---|
| U0 | Prerequisites | — | Admin team + operator |
| U2 | PDF tools, model check, verify, golden set | — (real samples needed for the golden set) | Engineering + Sudhanshu's team (review) |
| U3 | Pipeline to `FILED_PRIVATE` (dry run) | U2, U0 (Google access) | Engineering |
| U4 | Admin app | U3 | Engineering |
| U5 | Approve, publish, undo | U4 | Engineering |
| U6 | Metadata extraction (M1) | U5 | Engineering |
| U7 | Hardening and go-live | U6 | Engineering + operator |
| U8 | Chat agent loop migration to LangChain / LangGraph | U7 | Engineering |

There is no U1: the separate spike was dropped on 2026-10-06 and its model check moved into
U2 (see the worklog); the other numbers were kept. U2 contains the decision gate: if the
tools or the model cannot produce a clean document, the design changes before U3 starts.

---

## U0 — Prerequisites

Nothing here is code. Revised 2026-10-06 after talking to the admin team (Amarpreet).

**Asked of the admin team** (sent 2026-10-06):

- Create a Shared Drive, "Aura Agent", and add the operator as Manager. *(Done; the operator
  then created the `Unbranded` and `Test` folders — see Status below.)*
- Once the operator sends the service account email: add it to the Shared Drive as Content
  manager, and share the projects sheet with it as Editor.
- 3 real builder PDFs (one price list, one floor plan set, one site plan), with how they are
  unbranded by hand today and roughly how long each takes (the outcome baseline in
  EVALUATION.md).

**Done by the operator:**

- Create the Google Cloud project while signed in with the **company Workspace account**,
  not a personal Gmail; or have the admin create it and add the operator as Owner. Enable the
  Drive API and the Sheets API.
- Create the service account and a JSON key. If the org policy
  `iam.disableServiceAccountKeyCreation` blocks the key, ask the admin to allow it for this
  project. No domain-wide delegation.
- For local development, make a copy of the projects sheet. Until U3, dev runs with the
  operator's own Google login, against the `Test` folder and the sheet copy only, never the
  live sheet. Production uses only the service account.

**Not needed:** moving existing folders. Staff keep no PDFs in Drive for this today, so new
output starts in the new Shared Drive. Not used: the `office@` login, a new paid Workspace
user, or a personal / 2Creative account (see the worklog).

**Status (2026-10-06):** Shared Drive "Aura Agent" created, operator is Manager. Layout:

```
Aura Agent (Shared Drive)
  ├─ Unbranded   output root
  └─ Test        dry runs
```

| What | Drive ID | Config key |
|---|---|---|
| Shared Drive "Aura Agent" | `0AAos_9jUJ7hLUk9PVA` | `drive.shared_drive_id` |
| `Unbranded` folder (output root) | `1JzHRpjdghrbd3eVZgeDpXB3-Xkx6z4JX` | `drive.root_folder_id` |
| `Test` folder (dry runs) | `1HUH-DNChIiWnXF9KOjhszRDzBrI4Ucos` | `drive.test_root_folder_id` |

Open: Cloud project, the drive's "people outside the organisation" setting (a service
account counts as outside), service account and key, sheet copy, the 3 samples.

**Done when:** a short script using the service account key can list the `Test` folder,
upload a file into it, and read the `UNBRANDED` column of the sheet copy.

## U2 — PDF tools, model check, verify, golden set

Production code in Aura Chat. New dependencies `pymupdf` and `reportlab` (D8).

1. **Tools.** The M2 tools (LOOP.md) as a plain module with their guards: no word outside the
   source, no changed number, no near-full-page rect, render budget. Start with
   `render_page`, `get_text`, `redact_terms`, `redact_rect`, `delete_image`, `drop_page`,
   `add_mark`; `replace_line` and `rebuild_price_list` only when a sample needs them. Unit
   tests on small PDFs built inside the tests — no binaries in git, no network. Done
   2026-10-07: `tools.py` holds the guards; the PDF work is behind a second port,
   `PdfEditor` (pymupdf adapter). Boxes are on a 0–1000 grid.
2. **`verify()`** — built first, because every route needs it. Pure code over facts read
   through the `PdfInspector` port (pymupdf adapter): hit-list and generic text sweep,
   raw-object sweep, OCR in three modes, number integrity, word provenance, metadata strip,
   cover-up, page integrity (AUTONOMY.md). `scripts/unbrand_verify.py` runs it on a real
   pair by hand. OCR needs the tesseract binary, which the agent's startup script installs.
3. **Model check — the decision gate.** M2 as sort, pick, execute, judge, repair (LOOP.md,
   D23, revised 2026-10-08): `unbrand.py`, the `UnbrandModels` port and its LangChain adapter,
   prompts adapted from the `unbrand-builder-docs` skill. `scripts/unbrand_model_check.py`
   runs it on the real sample PDFs via OpenRouter, every role on Gemini 2.5 Flash first;
   `--expect-pages` compares the pages kept with what a person kept. Then a bake-off per role
   among cost-effective vision models with strict JSON schema on OpenRouter (Gemini 3.x
   Flash, Claude Haiku, Qwen); each role gets the cheapest model with no leak, no damage and
   the expected pages. Ask before spending on the bake-off.
   Done on the one sample, 2026-10-08 ([model-check.md](model-check.md)): sort on Gemini
   2.5 Flash, pick, judge and repair on Gemini 3.8 Flash with low thinking; a clean pass at
   $0.069 and 115 s. Still to run on a price list and a site plan.
   Sudhanshu's team reviews the outputs against what they produce by hand. Write a short
   note: leaks, damage, tool calls, wall time and cost per document, tools missing or
   unused. If the output is not clean, the design changes before U3.
4. **Golden set.** About 30 real documents, reviewed once by Sudhanshu's team from
   written instructions (pass or fail, what leaked, what was damaged). Their verdicts become
   the labels; stored outside git. Staff do not re-review on every change — the eval runner
   re-checks automatically.
5. **Eval runner.** Code checks on every case; M3 visual judge per page. How the judge is
   graded is decided at this point (INDEX.md open question 8).

**Done when:** `pytest -q` is green; the model check passed; and the eval runner passes
leak, integrity and provenance on every golden case with the chosen model.

## U3 — Pipeline to `FILED_PRIVATE` (dry run)

- `jobs` table and the job record (LOOP.md) — schema change, reviewed before it is applied.
- `JobStore` port with its Postgres adapter and a fake in `tests/fakes.py`.
- Worker inside the Aura Chat service: holds each job with a Postgres advisory lock (D19),
  one job at a time, runs the states `RECEIVED` → `UNBRANDING` → `VERIFYING` →
  `FILED_PRIVATE`. A step is a function of the job's status (D18), safe to rerun.
- The job's `instructions` (D21) reach M2. Model API errors handled as General errors (D22).
- Files on the Railway volume (D12): uploads, working copies, before and after renders;
  evicted `unbrander.retention_days` (default 30) after the job ends (D20).
- `GoogleWriter` port with its adapter: create folders, upload, keep private. Dry-run mode
  writes only under the test root.
- Admin-only API: create a job (upload + metadata typed by hand), get a job, list jobs.
- Input guardrails, budgets, audit log, `unbrander.enabled` switch (SECURITY.md).
- System dependencies: tesseract on Railway (`RAILPACK_DEPLOY_APT_PACKAGES=tesseract-ocr`),
  a local setup script (venv, pip install, `brew install tesseract`, `.env`), and a
  tesseract check in `/doctor`, so a deploy without OCR fails at boot rather than at the
  first PDF. verify() blocks every document when OCR cannot run.

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

## U8 — Chat agent loop migration to LangChain / LangGraph

Decided 2026-10-06; runs after Unbrander is live, so the migration has a working system and
a golden set to be measured against.

- Decide at the start: LangChain v1 (`create_agent`, which runs on LangGraph) or LangGraph
  directly. New dependency — approve before adding.
- Chat agent: a new `AgentRuntime` adapter replaces `agent_pydantic.py`. The port, `tools.py`,
  domain and the SSE contract the PWA reads stay unchanged.
- Unbrander already uses LangChain for its model calls (D10, revised 2026-10-07); nothing
  moves there. The pipeline stays a Postgres state machine (D18).
- Remove PydanticAI once nothing imports it.

**Done when:** `pytest -q` is green; the 50-question chat benchmark scores at least what it
scored before; the Unbrander eval suite passes with zero leaks; latency and cost per answer
are no worse than before, or the difference is accepted.
