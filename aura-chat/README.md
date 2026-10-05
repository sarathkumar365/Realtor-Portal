# Aura Chat

AI assistant for Aura Key Realty realtors. Reads the portal's project data over
the existing Apps Script API; stores its own conversations.

**New here? Read [how-it-works.md](../docs/aura-chat/how-it-works.md)** — the whole
system from process start to a finished answer, with every file explained.
Design rationale and rejected alternatives are in
[architecture.md](../docs/aura-chat/architecture.md).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env          # then fill TOKEN_SECRET
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --reload
```

`TOKEN_SECRET` must be byte-identical to the Script Property in the Apps Script
project. A mismatch means every realtor's token fails here while still working
in the portal — the symptom is a universal 401 with a healthy `/health`.

## The CLI

```bash
.venv/bin/uvicorn app.main:app --reload      # in one terminal
.venv/bin/aura login                         # portal ID + password, once
.venv/bin/aura                               # interactive
.venv/bin/aura "detached under $1M"          # one-shot
.venv/bin/aura --dev "…"                     # tools, timings, token usage
.venv/bin/aura --client "…"                  # as a buyer would see it
```

It goes over HTTP, like the PWA will — same login, same token, same SSE. A CLI
that reached into the app in-process would keep working while the endpoint was
broken, which is the one thing a client is meant to catch.

`login` stores only the returned token, in `~/.aura/session.json` at `0600`.
Never the password. `--token` and `AURA_TOKEN` override it.

In the REPL: `/new` clears the conversation, `/mode` switches realtor↔client,
`/dev` toggles the detailed view.

## Layout

| Path | Rule |
|---|---|
| `app/domain/` | the business shape. Imports nothing external. |
| `app/ports/` | Protocols only. Five seams, no more. |
| `app/adapters/` | one implementation per port. |
| `app/tools.py` | the AI's tools. Imports `domain` + `ports` only. |
| `app/agent.py` | the only file that may import an agent framework. |
| `app/container.py` | the only file that may construct an adapter. |

`tests/test_layering.py` enforces all of that. If it fails, the swap described
in the architecture doc has quietly stopped being a one-file change.

## Endpoints

All three take the realtor's own portal token as `Authorization: Bearer <token>`,
except `/health`. See [`../docs/aura-chat/operations.md`](../docs/aura-chat/operations.md)
for how to get one.

| | |
|---|---|
| `GET /health` | Public liveness. Returns `{status, ok}` only — deliberately uninformative, so a stranger cannot learn which secret is unset. |
| `GET /doctor` | The full diagnosis, for a signed-in human. `?fresh=1` rebuilds the caches. |
| `GET /me` | Proves the auth path end to end without touching project data. |
