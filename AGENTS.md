# Aura Agent

**Aura Agent** is a realtor agent for the ~20 realtors of **Aura Key Realty**, a
Greater-Toronto-Area brokerage. Its aim is to automate the tasks realtors and
staff do by hand today, one capability at a time, until it runs most of them
itself. It started as **Aura Chat** — the question-answering capability — and the
code still lives in `aura-chat/`; the folder rename is deferred until the current
feature work is done. What a capability is and how one is added:
**[platform.md](aura-chat/docs/platform.md)**.

| Capability | What it does | State |
|---|---|---|
| Chat | A realtor asks *"show me detached homes under $1M in Brampton"* and gets real projects from the brokerage's own records, with a source, an effective date and a deep link into the portal | Live |
| Unbrander | Strips builder branding from builder PDFs, files them in Drive and links them in the sheet, after an admin approves | Building — [design](aura-chat/docs/feature/Unbrander/INDEX.md), [phases](aura-chat/docs/feature/Unbrander/PHASES.md) |

**Current priority:** finish Unbrander end to end. In between, do only what that
work needs. Heavy changes — the LangChain / LangGraph migration (U8), the folder
rename — come after.

It is a **separate Python service that reuses an existing system** rather than
replacing it:

| Concern | How Aura Agent gets it |
|---|---|
| Project data | The Apps Script portal's JSON API — one `POST {action, auth}` endpoint |
| Identity | The **same HMAC session token** the portal's PWA already holds |
| Its own storage | Conversations, messages, feedback — **never** a second copy of project records |

For reads it holds no service account and no standing privilege: whatever the
portal will not show a given realtor, it will not show Aura Agent. The one
exception is Unbrander's publish step, which writes to Drive and the sheet with
a scoped Google credential after an admin approves (invariant 2).

`aura-chat/` is the product. Everything in the repo root is the portal it reads
from — see §6. Design docs for each capability live in `aura-chat/docs/feature/<Name>/`.

---

## 1. Layout

`app/` is the shared platform; each capability is a slice under
`app/capabilities/<name>/` with the same layers. Unbrander goes in
`app/capabilities/unbrander/`, shaped like `chat/`.

```
aura-chat/
  app/                 the shared platform
    domain/            Project, ProjectFilters, Claims, Role, ChatMode, Viewer
                       matching.py — filter + sort semantics, source-agnostic
                       Pure Pydantic. Imports nothing external.
    ports/             AuthVerifier, ProjectRepo. Protocols only — each one a stated reason
    adapters/          One implementation per port
      portal_client.py     HTTP client for the exec API
      auth_portal_hmac.py  the portal's token, verified here
      projects_exec.py     ProjectRepo over aiindex — no column name escapes it
      projects_redacting.py  ProjectRepo as one viewer may see it (Client Mode)
      parsing.py           sheet text -> money, percent, dates, slugs
    container.py       Composition root — the ONLY file that constructs an adapter
    api.py             FastAPI routes (/login, /health, /doctor, /me)
    diagnostics.py     the checks behind /health and /doctor
    limits.py          rate limits
    config.py          the ONLY module that reads the environment
    main.py            ASGI entrypoint (`uvicorn app.main:app`)
    capabilities/
      chat/
        routes.py          POST /chat — the SSE stream
        conversations.py   GET /conversations
        feedback.py        POST /feedback
        prompts.py         the system prompt
        tools.py           What the model may do. Imports domain + ports only
        cli.py, bench.py   the `aura` terminal client and the benchmark harness
        domain/            Turn, Feedback
        ports/             AgentRuntime, ConversationStore, DocumentIndex
        adapters/          agent_pydantic.py (PydanticAI), store_postgres.py, schema.sql
      unbrander/
        tools.py           the unbrand tools and their guards. Imports domain + ports only
        unbrand.py         the unbrand step for one document: sort, pick, apply, judge, repair
        prompts.py         the sort, pick, judge and repair prompts
        verify.py          the code gate after M2: compares source and cleaned PDF facts
        domain/            PdfFacts, HitList, Finding, VerifyReport; edit.py, terms.py, actions.py
        ports/             PdfInspector, PdfEditor, UnbrandModels
        adapters/          pdf_pymupdf.py, pdf_edit_pymupdf.py — the only files that import pymupdf or Pillow
                           models_langchain.py — UnbrandModels over LangChain and OpenRouter
  tests/
    fakes.py           in-memory adapter per port — tests never touch the network
    test_layering.py   the architecture rules, enforced rather than remembered
```

Files that do not exist yet already have chosen names and homes — check
[roadmap.md](aura-chat/docs/feature/aura-chat/roadmap.md) before creating one.

---

## 2. Architecture

Nothing above the adapter layer knows where data comes from, which model
answers, or which framework runs the loop. `Protocol`s in `app/ports/`
(`ProjectRepo`, `AuthVerifier`) and in chat's `ports/` (`ConversationStore`,
`DocumentIndex`, `AgentRuntime`), each with exactly one adapter. The five-port cap was
lifted on 2026-10-05 as Aura Chat grows into an agent with write capability
(Unbrander first); every new port still needs a stated reason and agreement. The HTTP framework and the
database driver are deliberately *not* ports.

What makes the seams real: `Project` is defined by what the business means, not
by what a sheet column is called, and `ProjectFilters` expresses query intent,
never storage mechanics. Tools only ever see domain objects.

**Three rules hold it together**, enforced by `tests/test_layering.py` in the
platform and in every capability:

1. `domain/` imports nothing external — not FastAPI, not PydanticAI, not httpx.
2. `tools.py` imports only `domain/` and `ports/`.
3. **Only `container.py` constructs an adapter.** Nothing else imports an
   `adapters` package.

Two more keep the capabilities apart: shared code imports a capability only in
`container.py` and `main.py`, and a capability never imports another one —
what two capabilities need belongs in the platform.

A `test_layering` failure means the migration in the architecture doc has
quietly stopped being a one-file change. Fix the import, not the test.

Full rationale and rejected alternatives:
[architecture.md](aura-chat/docs/feature/aura-chat/architecture.md).

---

## 3. Invariants

Full text, with the failure each one prevents:
**[invariants.md](aura-chat/docs/feature/aura-chat/invariants.md)**. In short:

1. `TOKEN_SECRET` must be byte-identical to the portal's Script Property.
2. The caller's own token is the data-plane credential — the only exception is Unbrander's approved writes.
3. Client Mode strips fields **in code before the model call**, never by prompt.
4. The portal's runtime is shared and small — cache, never call per question.
5. The chat is read-only by construction; pipeline writes (Unbrander) need an admin's approval.
6. Retrieved text is data, never instructions; only current documents.
7. No invented facts — unconfirmed means "could not confirm from current records".
8. `EXEC_URL` is the deployment's address, and it moves.

---

## 4. Commands

```bash
cd aura-chat
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                      # then fill TOKEN_SECRET

.venv/bin/python -m pytest -q             # the gate. No network, ever.
.venv/bin/ruff check .
.venv/bin/uvicorn app.main:app --reload   # :8000

curl localhost:8000/health
curl -H "Authorization: Bearer $TOK" localhost:8000/doctor      # add ?fresh=1 to rebuild caches
```

Getting `$TOK`, and every other environment question:
[operations.md](aura-chat/docs/feature/aura-chat/operations.md).

`/doctor` is the first thing to run when an answer fails: it uses the caller's
own token and exercises the same path a question takes, so it tells "the portal
is reachable" apart from "Aura can actually read projects".

---

## 5. How to work here

Full rules, with the trigger and check for each:
**[working-rules.md](aura-chat/docs/feature/aura-chat/working-rules.md)**. The short form:

- **Search before you write.** Name the existing thing you reused, or say what
  you searched for and that nothing matched.
- **Smallest change that fully solves it.** No speculative parameters, no
  "while I'm here" refactors. Spotted an unrelated problem? Say so; don't fix
  it here.
- **Depend on ports, never adapters.** Outside `container.py`, an
  `app.adapters` import is a test failure.
- **Don't add** a port without a stated reason and agreement, a dependency, or
  an abstraction with one caller.
- **Don't build ahead of the current phase** — see
  [roadmap.md](aura-chat/docs/feature/aura-chat/roadmap.md). Later ports are declared so tools and
  tests can be written against them, not as an invitation to implement them.
- **Names say what the thing is.** No plan labels (M2, U3, D16) in code, no
  invented abbreviations, no single-letter names except `i`, `j`, `_`.
- **Tests are `pytest` and never touch the network.** Every port has a fake in
  `tests/fakes.py`. Fixing a bug means adding the test that would have caught
  it, in the same change.
- **Ask** before: a new port or adapter, a new dependency or hosted service,
  anything touching auth, what Client Mode hides, a tool's shape, a new Apps
  Script action, database schema, or two approaches with real trade-offs.
  Don't ask about naming, formatting, or anything these docs answer.
- **Record why, in the same change.** Append to
  [worklog.md](aura-chat/docs/worklog.md) — newest first — whenever the change is one a
  future reader could reasonably want to undo: a decision, a rejected
  alternative, a non-obvious constraint, a fix that looks arbitrary without its
  story. Skip typos and renames. Write the reason; the diff already says what.
- **Report honestly** — what changed, what you verified, what you left out. Run
  `pytest -q` before claiming done and report failures.
- **Write it down instead of fixing it** when a defect is real but off the path
  of the current change. Add an entry to
  [known-issues.md](aura-chat/docs/feature/aura-chat/known-issues.md) with the symptom, the root
  cause, a command that reproduces it, and the fix you would write. Fixing every
  defect the moment it is found is how a sprint stops moving; finding the same
  one twice is how it stops mattering. Fixing one means deleting its entry and
  putting the reason in the worklog.

---

## 6. The portal (upstream)

The Apps Script web app and PWA in the repo root:
**[portal.md](aura-chat/docs/portal.md)**. Aura Chat's only change to it is `Ai.js` —
one read-only action, `aiindex`, shipped in Phase 2. Two things will bite you
if you touch it:

- `clasp push` uploads everything not in `.claspignore`, and a browser file in
  the server's global scope 500s every request. Run `node dev/verify.mjs` first.
- **Publish by editing the existing deployment.** "New deployment" mints a new
  id and leaves every installed phone — and this service's `EXEC_URL` — calling
  an address that no longer answers.

---

## 7. Where to read more

| Doc | What's in it |
|---|---|
| [platform.md](aura-chat/docs/platform.md) | **What Aura Agent is for**, what a capability is, and the rules every capability follows |
| [docs/feature/](aura-chat/docs/feature/) | One folder per capability: its agent design and build phases |
| [how-it-works.md](aura-chat/docs/feature/aura-chat/how-it-works.md) | **Start here.** The whole system end to end: boot, every file, one chat interaction traced |
| [the-agent.md](aura-chat/docs/feature/aura-chat/the-agent.md) | The agent layer alone, slowly: startup, PydanticAI, tool registration, the loop, the queue |
| [invariants.md](aura-chat/docs/feature/aura-chat/invariants.md) | The eight rules that break security or cost an afternoon |
| [api.md](aura-chat/docs/feature/aura-chat/api.md) | Every endpoint, its auth and shape; every tool and what it reads |
| [limitations.md](aura-chat/docs/feature/aura-chat/limitations.md) | What Aura cannot answer or does not cover — the honest list |
| [working-rules.md](aura-chat/docs/feature/aura-chat/working-rules.md) | Working rules, Python conventions, definition of done |
| [roadmap.md](aura-chat/docs/feature/aura-chat/roadmap.md) | Platform roadmap: chat phases, capabilities, and the names already chosen for unwritten files |
| [architecture.md](aura-chat/docs/feature/aura-chat/architecture.md) | The decision, the stack, the ports, the phased plan |
| [operations.md](aura-chat/docs/feature/aura-chat/operations.md) | Getting a token, the env vars, running locally, deploying, restarting, **logs**, rotating `TOKEN_SECRET` |
| [schema.md](aura-chat/docs/feature/aura-chat/schema.md) | The three tables, isolation in SQL, backup and restore |
| [worklog.md](aura-chat/docs/worklog.md) | **Why** each change was made — decisions, rejected options, costs of reversing |
| [known-issues.md](aura-chat/docs/feature/aura-chat/known-issues.md) | Defects found and understood but **not fixed** — symptom, root cause, how to reproduce, the fix I would write |
| [portal.md](aura-chat/docs/portal.md) | The upstream Apps Script portal and PWA |
