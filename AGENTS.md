# Aura Chat

**Aura Chat** is an AI assistant for the ~20 realtors of **Aura Key Realty**, a
Greater-Toronto-Area brokerage. A realtor asks *"show me detached homes under
$1M in Brampton"* and gets real projects from the brokerage's own records, with
a source, an effective date, and a deep link into the project page they already
use.

It is a **separate Python service that reuses an existing system** rather than
replacing it:

| Concern | How Aura Chat gets it |
|---|---|
| Project data | The Apps Script portal's JSON API — one `POST {action, auth}` endpoint |
| Identity | The **same HMAC session token** the portal's PWA already holds |
| Its own storage | Conversations, messages, feedback — **never** a second copy of project records |

It holds no service account, no Sheets credential, and no standing privilege.
Whatever the portal will not show a given realtor, it will not show Aura Chat.

`aura-chat/` is the product. Everything in the repo root is the portal it reads
from — see §6.

---

## 1. Layout

```
aura-chat/
  app/
    domain/            Project, ProjectFilters, Claims, Role, ChatMode
                       matching.py — filter + sort semantics, source-agnostic
                       Pure Pydantic. Imports nothing external.
    ports/             Protocols only — five seams, no more
    adapters/          One implementation per port
      portal_client.py     HTTP client for the exec API
      auth_portal_hmac.py  the portal's token, verified here
      projects_exec.py     ProjectRepo over aiindex — no column name escapes it
      parsing.py           sheet text -> money, percent, dates, slugs
    tools.py           What the model may do. Imports domain + ports only
    container.py       Composition root — the ONLY file that constructs an adapter
    api.py             FastAPI routes (/health, /doctor, /me)
    diagnostics.py     the checks behind /health and /doctor
    config.py          the ONLY module that reads the environment
    main.py            ASGI entrypoint (`uvicorn app.main:app`)
  tests/
    fakes.py           in-memory adapter per port — tests never touch the network
    test_layering.py   the architecture rules, enforced rather than remembered
```

Files that do not exist yet already have chosen names and homes — check
[roadmap.md](docs/aura-chat/roadmap.md) before creating one.

---

## 2. Architecture

Nothing above the adapter layer knows where data comes from, which model
answers, or which framework runs the loop. Five `Protocol`s in `app/ports/` —
`ProjectRepo`, `AuthVerifier`, `ConversationStore`, `DocumentIndex`,
`AgentRuntime` — each with exactly one adapter. The HTTP framework and the
database driver are deliberately *not* ports.

What makes the seams real: `Project` is defined by what the business means, not
by what a sheet column is called, and `ProjectFilters` expresses query intent,
never storage mechanics. Tools only ever see domain objects.

**Three rules hold it together**, enforced by `tests/test_layering.py`:

1. `domain/` imports nothing external — not FastAPI, not PydanticAI, not httpx.
2. `tools.py` imports only `domain/` and `ports/`.
3. **Only `container.py` constructs an adapter.** Nothing else imports
   `app.adapters`.

A `test_layering` failure means the migration in the architecture doc has
quietly stopped being a one-file change. Fix the import, not the test.

Full rationale and rejected alternatives:
[architecture.md](docs/aura-chat/architecture.md).

---

## 3. Invariants

Full text, with the failure each one prevents:
**[invariants.md](docs/aura-chat/invariants.md)**. In short:

1. `TOKEN_SECRET` must be byte-identical to the portal's Script Property.
2. The caller's own token is the data-plane credential — never a service account.
3. Client Mode strips fields **in code before the model call**, never by prompt.
4. The portal's runtime is shared and small — cache, never call per question.
5. V1 is read-only by construction.
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
[operations.md](docs/aura-chat/operations.md).

`/doctor` is the first thing to run when an answer fails: it uses the caller's
own token and exercises the same path a question takes, so it tells "the portal
is reachable" apart from "Aura can actually read projects".

---

## 5. How to work here

Full rules, with the trigger and check for each:
**[working-rules.md](docs/aura-chat/working-rules.md)**. The short form:

- **Search before you write.** Name the existing thing you reused, or say what
  you searched for and that nothing matched.
- **Smallest change that fully solves it.** No speculative parameters, no
  "while I'm here" refactors. Spotted an unrelated problem? Say so; don't fix
  it here.
- **Depend on ports, never adapters.** Outside `container.py`, an
  `app.adapters` import is a test failure.
- **Don't add** a port (five, hard cap), a dependency, or an abstraction with
  one caller.
- **Don't build ahead of the current phase** — see
  [roadmap.md](docs/aura-chat/roadmap.md). Later ports are declared so tools and
  tests can be written against them, not as an invitation to implement them.
- **Tests are `pytest` and never touch the network.** Every port has a fake in
  `tests/fakes.py`. Fixing a bug means adding the test that would have caught
  it, in the same change.
- **Ask** before: a new port or adapter, a new dependency or hosted service,
  anything touching auth, what Client Mode hides, a tool's shape, a new Apps
  Script action, database schema, or two approaches with real trade-offs.
  Don't ask about naming, formatting, or anything these docs answer.
- **Record why, in the same change.** Append to
  [worklog.md](docs/worklog.md) — newest first — whenever the change is one a
  future reader could reasonably want to undo: a decision, a rejected
  alternative, a non-obvious constraint, a fix that looks arbitrary without its
  story. Skip typos and renames. Write the reason; the diff already says what.
- **Report honestly** — what changed, what you verified, what you left out. Run
  `pytest -q` before claiming done and report failures.
- **Write it down instead of fixing it** when a defect is real but off the path
  of the current change. Add an entry to
  [known-issues.md](docs/aura-chat/known-issues.md) with the symptom, the root
  cause, a command that reproduces it, and the fix you would write. Fixing every
  defect the moment it is found is how a sprint stops moving; finding the same
  one twice is how it stops mattering. Fixing one means deleting its entry and
  putting the reason in the worklog.

---

## 6. The portal (upstream)

The Apps Script web app and PWA in the repo root:
**[portal.md](docs/portal.md)**. Aura Chat's only change to it is `Ai.js` —
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
| [how-it-works.md](docs/aura-chat/how-it-works.md) | **Start here.** The whole system end to end: boot, every file, one chat interaction traced |
| [the-agent.md](docs/aura-chat/the-agent.md) | The agent layer alone, slowly: startup, PydanticAI, tool registration, the loop, the queue |
| [invariants.md](docs/aura-chat/invariants.md) | The eight rules that break security or cost an afternoon |
| [api.md](docs/aura-chat/api.md) | Every endpoint, its auth and shape; every tool and what it reads |
| [limitations.md](docs/aura-chat/limitations.md) | What Aura cannot answer or does not cover — the honest list |
| [working-rules.md](docs/aura-chat/working-rules.md) | Working rules, Python conventions, definition of done |
| [roadmap.md](docs/aura-chat/roadmap.md) | Phase status, and the names already chosen for unwritten files |
| [architecture.md](docs/aura-chat/architecture.md) | The decision, the stack, the ports, the phased plan |
| [investigation-aur-3-4-5.md](docs/aura-chat/investigation-aur-3-4-5.md) | The discovery it rests on |
| [operations.md](docs/aura-chat/operations.md) | Getting a token, the env vars, running locally, deploying, restarting, **logs**, rotating `TOKEN_SECRET` |
| [schema.md](docs/aura-chat/schema.md) | The three tables, isolation in SQL, backup and restore |
| [worklog.md](docs/worklog.md) | **Why** each change was made — decisions, rejected options, costs of reversing |
| [known-issues.md](docs/aura-chat/known-issues.md) | Defects found and understood but **not fixed** — symptom, root cause, how to reproduce, the fix I would write |
| [sprint-tracker.html](docs/aura-chat/sprint-tracker.html) | The AUR-* sprint board. Reference only — nothing reads it |
| [portal.md](docs/portal.md) | The upstream Apps Script portal and PWA |
