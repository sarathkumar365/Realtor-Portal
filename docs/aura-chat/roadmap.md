# Aura Chat — build state and planned files

What is wired, what is next, and the names already chosen for files that do not
exist yet. Phase detail and done-signals live in
[`architecture.md`](architecture.md) §5. Referenced from
[`../../AGENTS.md`](../../AGENTS.md).

---

## Where the build actually is

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
