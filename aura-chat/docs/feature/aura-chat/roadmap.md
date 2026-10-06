# Aura Agent — roadmap and planned files

What is wired, what is next, and the names already chosen for files that do not
exist yet. Aura Agent grows one capability at a time
([`../platform.md`](../../platform.md)); the first capability, Chat, was built in
Phases 1–6 below (detail and done-signals in [`architecture.md`](architecture.md)
§5). Later capabilities carry their own phases in `aura-chat/docs/feature/<Name>/`.
Referenced from [`../../AGENTS.md`](../../../../AGENTS.md).

## Capabilities

| Capability | Phases | State |
|---|---|---|
| Chat | 1–6 below | Live; Phase 5 not started, Phase 6 part done |
| Unbrander | U0–U8, [`PHASES.md`](../Unbrander/PHASES.md) | **Current priority** — designing done, build next |
| Next capabilities | — | To be added after Unbrander |

---

## Chat — where the build actually is

`Container` is the honest status board: a field that is `None` is a phase that
has not shipped, and `/health` and `/doctor` report those as `null`, not as
failures.

| Phase | Scope | State |
|---|---|---|
| 1 | Skeleton, config, auth, portal client, `/health` `/doctor` `/me` | **done** |
| 2 | `aiindex` action (`Ai.js`), `projects_exec.py`, parsing, matching, four tools | **done** — 116 tests green |
| 3 | `agent.py`, SSE endpoint, chat screen in the PWA — **the Day 1 gate** | **done** — 232 tests green. Not yet deployed: the service needs an HTTPS host and its origin in `ALLOWED_ORIGINS`, and the real-device matrix is unrun |
| 4a | Postgres persistence, server-side history, isolation, feedback storage | **done** — 292 tests green, plus two integration scripts against a real database |
| 4b | History panel, New Chat list, admin reports screen | **done** — 4b built the reports screen rather than a conversation browser; see the worklog |
| 5 | Document retrieval over pgvector; structured-first | not started |
| 6 | Audit logging, chat-specific rate limit, latency, 50-question benchmark | **part done** — audit logging (AUR-20) and the rate limit (AUR-21) shipped; latency measured; the benchmark is at 44/50 against a bar of 47 |
| U | **Unbrander** — builder-document unbranding, the first write feature, with a separate admin app (Aura Agent UI) | **designing** — see [`docs/feature/Unbrander/Docs/agent/`](../Unbrander/INDEX.md). Phases U0–U7 in [`PHASES.md`](../Unbrander/PHASES.md) |
| L | Move the agent loop from PydanticAI to LangChain / LangGraph | **decided 2026-10-06; phase U8**, after Unbrander goes live — see [`PHASES.md`](../Unbrander/PHASES.md) |

Phase 2 shipped one outstanding check: reading real rows needs a realtor token,
which the session that built it did not have. See
[`operations.md`](operations.md) for how to get one.

**Do not build ahead of the current phase.** The ports for later phases are
declared so tools and tests can be written against them — that is not an
invitation to implement them early.

---

## Files not written yet, already named

Use these names and locations; do not invent alternatives. If what you need is
not on this list, that is a design decision — ask.

| File | Phase | What it is |
|---|---|---|
| `app/agent.py` | 3 | The **only** file permitted to import an agent framework |
| ~~`app/adapters/store_postgres.py`~~ | 4 | **written** — `ConversationStore` on Railway Postgres |
| `app/adapters/docs_pgvector.py` | 5 | `DocumentIndex` |

**`app/adapters/filters.py` was planned and deliberately not built.** Filtering
became `app/domain/matching.py` (`matches`, `sort_key` — pure, source-agnostic,
so a future SQL adapter reuses the semantics), and the TTL cache went inside
`ExecApiProjectRepo`, because a Postgres adapter would not want it. See the
worklog entry for 2026-08-24.
