# Aura Chat — Architecture Decision & Build Plan

**Date:** 2026-08-24 · **Owner:** Sarath · **Status:** proposed, awaiting approval
**Companion doc:** [investigation-aur-3-4-5.md](investigation-aur-3-4-5.md) — the discovery this rests on.

---

## 1. Decision

Aura Chat is a **separate Python service**. It reuses the portal's data and auth over the
existing Apps Script API; it does not fork the portal, duplicate the Sheets, or live inside
Apps Script.

```
┌────────────────────┐   SSE    ┌──────────────────────┐   HTTPS   ┌──────────────┐
│  Aura Key PWA      │ ───────► │  Aura Chat service   │ ────────► │  OpenRouter  │
│  (www/, existing)  │ ◄─────── │  FastAPI + PydanticAI│ ◄──────── │  (any model) │
│  new: chat screen  │          │  on Railway          │           └──────────────┘
└────────────────────┘          └───────┬──────────┬───┘
                                        │          │
                        POST {action,   │          │  asyncpg
                        auth} — the     │          ▼
                        SAME exec API   │   ┌──────────────┐
                                        ▼   │  Supabase    │
                             ┌──────────────┴───┐ Postgres │
                             │  Apps Script     │ +pgvector│
                             │  Core/Sheets/Team│ └──────────┘
                             └────────┬─────────┘
                                      ▼
                             Google Sheets ×3
```

### Chosen over

| Option | Why not |
|---|---|
| **All inside Apps Script** | No SSE streaming (`ContentService` buffers). ~60s per `UrlFetch`. **90 min/day runtime shared with the portal** — chat traffic could take Home down. Blocks every Future ticket (RAG, webhooks, push). |
| **Cloudflare Worker + D1** | Genuinely good and cheaper. Rejected on familiarity: a non-Node runtime with package quirks is the wrong thing to be learning during a 2-day sprint. Revisit later — Hono/FastAPI both port. |
| **Vercel / Next.js rebuild** | The PWA already delivers phone + web + install + offline + auth. A rebuilt frontend buys nothing. |
| **Vertex AI Agent Builder / Azure AI Foundry** | Hosts the loop, but the hard parts here — Client-Mode field filtering, our HMAC auth, the sheet schema — stay our code regardless. Realtors have no Google/MS identity, so their auth and embed models fight ours. Metered (sessions ~$0.25/1k events, search $1.50–6/1k queries) plus hard lock-in, for ~20 users. Reconsider only if the business standardises on GCP/Azure. |

---

## 2. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | **Python 3.12** | Sarath's preference; agent ecosystem is Python-first |
| API | **FastAPI** | native SSE via `StreamingResponse`; typed; boring |
| Agent loop | **PydanticAI** | tool loop + streaming built in; Pydantic validation *is* the AUR-33 guardrail; model is a config string (AUR-9/10) |
| Model access | **OpenRouter** | one API, 300+ models, full SSE + tool calling |
| DB | **Supabase Postgres** | conversations, messages, feedback, audit; `pgvector` already present for future RAG |
| DB access | **asyncpg + SQLModel** | no ORM ceremony |
| Host | **Railway** | usage-based, ≈$2–5/mo for an app idle most of the day |
| Project data | **the existing Apps Script exec API** | zero re-implementation of readers, cache, permissions; no Sheets API quota exposure |
| Auth | **port of `checkToken_`** (~15 lines HMAC) | same `TOKEN_SECRET`, same token the PWA already holds |

### Not chosen

- **LangChain / LangGraph** — built for 300+ integrations and graph orchestration. This agent has 5 tools and one loop. Cost is debuggability: a misbehaving tool call means debugging their abstraction stack, not ours.
- **Raw `openai` SDK + hand-rolled loop** — ~100 lines, zero framework risk. Defensible; PydanticAI wins on streaming + multi-step tools + validation. If PydanticAI disappoints, this is the fallback and it is cheap.

---

## 3. Two design decisions worth stating explicitly

### 3.1 The user's own token is the data-plane credential

The service **forwards the realtor's token** to the exec API. It holds no service account and
has no standing privilege.

- Permissions are enforced by code that already exists (e.g. builder logins are admin-only).
- A revoked realtor loses Aura Chat within the same 5-minute window as the portal.
- Nothing new to audit: `TOKEN_SECRET` gains one more holder, and that is the whole delta.

### 3.2 Filter in Python, not in Apps Script

`getSearchIndex_` already builds a warm, cached, cross-city array. Rather than push filter
logic into Apps Script:

- Add **one** new action, `aiindex`, returning that array.
- The service pulls it on a short TTL (5–10 min) and filters in Python.

Why: richer filtering (numeric ranges, multi-field), no Apps Script logic to keep in sync, and
**far less portal runtime consumed** — one fetch per TTL window instead of one per question.

---

## 4. Pluggability — ports and adapters

**Principle: nothing in the core knows where data comes from, which model answers, or which
agent framework runs the loop.** Every external dependency sits behind a `Protocol`, with one
adapter today and room for another later.

### 4.1 The seams

| Port | Adapter today | Plausible replacement |
|---|---|---|
| `ProjectRepo` | Apps Script exec API → Sheets | Postgres, a real CRM, an internal API |
| `ConversationStore` | Supabase Postgres | any SQL, Firestore, Redis |
| `DocumentIndex` | pgvector | Qdrant, Vertex Search, Azure AI Search |
| `AuthVerifier` | portal HMAC token | OAuth/SSO if the business moves to Google identities |
| `AgentRuntime` | PydanticAI | LangGraph, OpenAI Agents SDK, hand-rolled loop |

Five, not six. Deliberately **not** abstracted:

- **The model provider.** Swapping OpenRouter for Gemini direct is already a model string inside
  the runtime — a port would wrap an abstraction that exists. Swapping the *loop* is what
  `AgentRuntime` is for.
- **The HTTP framework and the Postgres driver.** Neither will ever be swapped.

A seam that will never gain a second adapter is cost with no return.

### 4.2 What makes the data-source swap real

A source-agnostic **domain model**. `Project` is a Pydantic model defined by what the business
means, not by what a sheet column is called. Each adapter maps its own storage into it.

- Sheets adapter: `"STARTING PRICE" → Project.starting_price: int | None`
- Future Postgres adapter: `row["starting_price"] → the same field`
- **Tools only ever see `Project`.** They never learn a tab name, a row number or a column header.

Equally important: ports are written in terms of **query intent**, not storage mechanics.

```python
class ProjectRepo(Protocol):
    async def search(self, f: ProjectFilters) -> list[Project]: ...
    async def get(self, project_id: str) -> Project | None: ...
    async def recent(self, days: int) -> list[Project]: ...
```

Not `read_tab()`, not `run_sql()`. A `ProjectFilters` object in, domain objects out — which is
implementable against a sheet, a table, or an API without changing a single caller.

### 4.3 Migration path this buys

Moving project data off Sheets later becomes a config change, not a rewrite:

1. Add `projects_postgres.py` implementing the same port
2. Mirror Sheets → Postgres on a schedule (a third adapter can wrap both and dual-read)
3. Flip `PROJECT_SOURCE=postgres`
4. Delete the old adapter once confident

Tools, prompts, agent, API and UI are untouched throughout.

### 4.4 Repo layout

```
aura-chat/
  app/
    domain/        Project, ProjectFilters, Claims, Role, ChatMode
                   later: Document, Conversation, Message (phases 4-5)
                   pure Pydantic — no I/O, no framework, no vendor types
    ports/         Protocols only: ProjectRepo, ConversationStore, DocumentIndex,
                   AuthVerifier, AgentRuntime — five, and no more
    adapters/
      portal_client.py     HTTP client for the exec API
      projects_exec.py     ProjectRepo over that client ← today
      store_postgres.py    conversations, messages, feedback
      docs_pgvector.py     document retrieval
      auth_portal_hmac.py  port of checkToken_
    tools.py       plain async functions; depend on PORTS only
    agent.py       PydanticAI wiring   ← the ONLY file importing an agent framework
    api.py         FastAPI routes + SSE
    container.py   composition root: reads config, picks adapters, injects
    config.py      env only
  tests/
    fakes.py       in-memory adapters for every port — tests never touch network
```

### 4.5 The three rules that keep it honest

1. **`domain/` imports nothing** — not FastAPI, not PydanticAI, not asyncpg.
2. **`tools.py` imports only `domain/` and `ports/`** — never an adapter, never a framework.
3. **Adapters are constructed in exactly one place**, `container.py`. No module reaches for a
   global client.

Enforcement is a grep in CI, not a convention people remember.

### 4.6 Honest cost

Five ports plus a composition root is roughly a day of scaffolding that a direct implementation
would not spend. It is worth it here because two of the swaps are *likely*, not hypothetical:
the project data is expected to outgrow Sheets, and the agent framework is a fresh bet.

The discipline to hold: **one adapter per port during the sprint.** Interfaces now, alternatives
only when a second is actually needed. Ports are a seam, not a plugin marketplace.

## 5. Phased plan

Each phase is independently reviewable and has a stated done-signal.

### Phase 0 — Prerequisites (before any code)

| Item | Owner | Blocks |
|---|---|---|
| `TOKEN_SECRET` / `PASSWORD_PEPPER` / `ADMIN_PASSCODE` confirmed set (`checkSecret()`) | Sarath | everything |
| Apps Script account tier confirmed (consumer 90 min/day vs Workspace 6 h) | Sarath | AUR-21 sizing |
| `PROJECT ID` column added, priority projects | Sudhanshu | AUR-26/27/47/54/79 |
| Commercial columns (price, deposit, bedrooms…) | Sudhanshu | AUR-25 filters, Day 1 gate |

**Done:** all four answered. Items 3–4 may land late; §7 covers building without them.

### Phase 1 — Service skeleton + auth  (AUR-13, 14, 22, 9) ✅ **done 2026-08-24**

- `domain/` + `ports/` defined first — `Project`, `ProjectFilters`, and the six Protocols
- `container.py` composition root; config from env only, no secrets in code
- FastAPI app, `/health` reporting app / exec API / model reachability
- `auth_portal_hmac.py`: verify HMAC token, reject anything unsigned or expired
- `portal_client.py`: POST client for the exec API, token pass-through
- `tests/fakes.py`: in-memory adapter per port
- Deploy to Railway, HTTPS

**Done:** `/health` green from the internet; an authenticated round trip to the exec API returns real city data; an unsigned request is refused; the test suite passes against fakes with no network.

**Verified 2026-08-24:** 28 tests green. Live call to the deployed exec API returns
`{"ok":false,"error":"login required"}` — the data plane works, redirects included.
`/health` → `{"ok":true,"checks":{"app":true,"auth_configured":true,"portal":true,"model":null}}`.

### Phase 2 — Tools over live data  (AUR-16, 17, 19, 25, 26, 27, 28) ✅ **done 2026-08-24**

- New Apps Script action `aiindex` (read-only)
- `filters.py`: TTL cache + numeric/categorical filtering
- `projects_exec.py` maps sheet headers → `Project`; no column name escapes the adapter
- `tools.py`: `searchProjects`, `getProject`, `getRecentProjects` as plain typed functions over `ProjectRepo`
- Record-scoped: only the returned rows are ever passed to the model
- Read-only by construction: no tool takes a write path

**Done:** a direct call to `searchProjects(city="BRAMPTON", cats=["detached"])` returns real Aura projects. No model involved yet.

**Verified 2026-08-24:** 116 tests green; `dev/verify.mjs` resolves `aiindex` to `getAiIndex_`; the action is live and token-gated. Reading real rows needs a realtor token, which was not available in this session — that is the one outstanding check.

AUR-15 (tool router) and AUR-34 (natural-language brief → one correct call) moved to Phase 3: both need the model.

### Phase 3 — Agent + chat UI → **Day 1 gate**  (AUR-33, 35, 41–47, 96)

- `agent.py`: PydanticAI agent, tools registered, `stopWhen` step cap
- System prompt with the no-invention guardrail; unconfirmed → "could not confirm from current records"
- SSE endpoint; chat screen added to `www/` as a new route in `LOAD`
- Structured result cards; `View Project` deep link
- Follow-up context over the previous result set

**Done — this is AUR-96:** sign in → ask "show detached under $1M" → real Aura projects → tap one → the project page opens.

### Phase 4 — Persistence, modes, sources  (AUR-18, 27, 36–40, 48, 49, 51, 55–57, 59–62, 32)

- Postgres schema: `ai_conversations`, `ai_messages`, `feedback`
- New Chat + history; continues across devices; server-side user isolation
- `compareProjects`
- **Client Mode**: confidential fields stripped **in code before the model call**, never by prompt
- Source block: document + effective date; `View Source`
- Helpful / Incorrect + Report Data Issue

**Done:** Tue 12:00 demo — persistence, comparison, Client Mode, sources (AUR-97).

### Phase 5 — Document retrieval  (AUR-29, 30, 23)

- Small curated corpus: current price sheet + brochure per priority project
- `pypdf` → chunk → embed → `pgvector`
- `IsCurrent = TRUE` only; superseded documents excluded
- Retrieved text delimited and treated as data — never as instructions
- **Structured-first**: this tool runs only when the columns cannot answer

**Done:** a brochure-only question answers with a source and effective date; an April price sheet is never quoted as current.

### Phase 6 — Harden, deploy, QA  (AUR-20, 21, 24, 65–68, 76–81, 82–93)

- Audit logging: who asked what, which tools ran, what returned
- Rate limiting **on its own counter**, so chat can starve without taking the portal with it
- Latency tuning to the <10 s target
- 50-question benchmark; root-cause every failure
- Handoff docs

**Done:** ≥47/50, zero invented prices, 100% correct deep links, deployed and stable.

---

## 6. Non-goals

- Not rebuilding the portal, the PWA, or AppSheet
- Not migrating the Sheets to a database — Sheets stay the source of truth for project data
- No writes of any kind in V1
- No fine-tuning, no custom training, no local model hosting
- No Kubernetes, no message queue, no microservices
- Postgres holds **conversations and derived data only** — never a second copy of project records
- No plugin system, no dynamic adapter loading, no config DSL — ports are compile-time seams, wired in one file

---

## 7. Risks

| Risk | Detection signal | Mitigation |
|---|---|---|
| **Commercial columns never arrive** | Sudhanshu's reply Monday AM | Build Phases 1–3 against columns that exist (city, builder, type, occupancy, status). Tool signatures do not change when price lands. Escalate scope to the business owner. |
| **Chat traffic starves the portal's runtime** | Home slow/failing; Apps Script quota page | `aiindex` TTL cache means ~1 fetch per 10 min, not per question. Chat-specific rate limit (AUR-21). |
| **PydanticAI friction** | Fighting the framework more than the problem, by Phase 3 | Fall back to raw `openai` SDK + hand-rolled loop, ~100 lines. Only `agent.py` changes — `tools.py`, ports and domain are unaffected. |
| **Over-abstraction** | Ports with one adapter that will never gain a second; indirection slowing Day 1 | Six ports, hard cap. One adapter each during the sprint. No plugin registry, no dynamic loading. |
| **Supabase free tier pauses after ~7 days idle** | Chat history 500s after a quiet week | Daily use keeps it alive; $25/mo removes it; or move Postgres to Railway alongside the app. |
| **Railway has no spend cap by default** | Surprise bill | Set a usage limit on day one. |
| **Phase 5 slips** | Not started by Tue midday | It is the designated cut. AUR-16 makes it the fallback path, so the MVP stands without it. |
| **`TOKEN_SECRET` now lives in two places** | — | Both are managed secret stores. Rotation means updating two, not one — document it in the handoff. |

---

## 8. Validation criteria

- **Day 1 gate (AUR-96)** — login → "show detached under $1M" → real projects → tap → project page
- **Accuracy (AUR-78)** — ≥95%, zero invented prices or deposits
- **Deep links (AUR-79)** — 100% resolve to the correct project
- **Follow-up context (AUR-80)** — ≥95% across multi-turn benchmark conversations
- **Client Mode (AUR-58)** — zero leaks under deliberate probing
- **Latency (AUR-65)** — <10 s end to end for normal questions
- **Benchmark (AUR-76)** — ≥47/50

---

## 9. Board impact

- **Obsolete under this architecture** — already cancelled: AUR-2, 6, 7, 8, 12, 85
- **New Apps Script work** — one read-only action (`aiindex`); no changes to existing readers
- **New ticket needed** — "Expose `aiindex` action" as a dependency of AUR-25
- **AUR-13 changes shape** — from "scaffold a service" to "scaffold FastAPI on Railway"; same ticket, same position on the critical path

---

## 10. Open questions

1. **Is the commercial data anywhere?** — with Sudhanshu; decides whether Phase 2 filters are real on Day 1
2. **Account tier** — consumer or Workspace; sizes the runtime risk
3. **PydanticAI or raw SDK** — defaulting to PydanticAI; reversible at one file
