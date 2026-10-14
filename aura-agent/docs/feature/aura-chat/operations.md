# Aura Chat — operations

Everything environmental: getting a token, what each setting does, deploying,
and rotating the one secret whose failure is invisible. Referenced from
[`../../AGENTS.md`](../../../../AGENTS.md).

---

## 1. Getting a portal token

`/doctor`, `/me` and every tool call need a realtor's own session token — this
service holds no credential of its own, so there is no way around having one.
Two ways to get it.

**Mint one against the portal.** `login` is a public action, so this needs only
a real Portal ID and password:

```bash
EXEC=$(grep -o "https://script.google.com/[^']*" aura-agent/portal/dev/config.mjs | head -1)
curl -sL "$EXEC" -H 'Content-Type: text/plain;charset=utf-8' \
  -d '{"action":"login","username":"YOUR_ID","password":"YOUR_PASSWORD"}'
```

Answers `{"ok":true,"name":…,"role":"realtor","token":"…"}`.

Two details that are the difference between JSON and a wall of Google HTML.
`-L`, because Apps Script answers a POST with a 302 and serves the body from
`script.googleusercontent.com`. And **no `-X POST`** — `-d` already makes it a
POST, while `-X` pins the method across the redirect too, and that second hop
only answers GET. With `-X POST` you get a 405 and an HTML error page.

**Or lift it from the admin app.** Signed in, in its devtools console:

```js
JSON.parse(sessionStorage.getItem('aura-agent.session')).token
```

The admin app keeps only admin tokens, so for a realtor's view mint one with
`login` above.

Then:

```bash
TOK='<paste>'
curl -s -H "Authorization: Bearer $TOK" localhost:8000/doctor | python3 -m json.tool
```

A token is valid for 7 days from issue, and the portal's `session` action
re-issues it. It carries the realtor's role, so an admin token and a realtor token
see different things — test with the one whose experience you are debugging.

**Never paste a token into a commit, a doc, an issue, or a log line.** It is a
bearer credential for that realtor's whole account.

---

## 2. Settings

Every one is read in `app/config.py` and nowhere else. `.env` is git-ignored;
`.env.example` is the template.

| Variable | Default | What it does |
|---|---|---|
| `TOKEN_SECRET` | *(none — refuses)* | HMAC key for portal session tokens. See §5. |
| `EXEC_URL` | *(none)* | The deployed Apps Script web app. Must equal `EXEC` in `aura-agent/portal/dev/config.mjs`. |
| `EXEC_TIMEOUT_S` | `30.0` | Per-request timeout against the portal. Cold index builds are slow; see [`portal.md`](../../portal.md) §4.5. |
| `SESSION_MS` | `604800000` (7 days) | Token lifetime. **Must match `SESSION_MS` in `Core.js`** — longer here keeps honouring tokens the portal has retired. |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS allowlist. Every browser client's origin **must** be in here or the browser blocks the request before it leaves the page. Today that is only the admin app: `http://localhost:5173` for `npm run dev`, and its site's origin once it is deployed. Never `*`: a wildcard lets any page a realtor visits spend their token. |
| `ALLOWED_ORIGIN_REGEX` | *(empty)* | Only for Netlify deploy previews, which get a random subdomain per draft deploy and so cannot be named in the list. A standing hole in the allowlist — set it while testing previews, unset it after. |
| `OPENROUTER_API_KEY` | *(none)* | Phase 3. |
| `LLM_MODEL` | `google/gemini-2.5-flash` | A model swap is this string. See §2.1. |
| `LLM_MAX_TOKENS` | `1500` | A ceiling on the answer, not a target. Left unset, providers advertise their whole context as `max_tokens` — 65k on Gemini Flash — which OpenRouter bills against up front, so a request can be refused for lack of credit to cover an answer nobody wanted. |
| `CHAT_PER_HOUR` | `60` | Questions per **user** per hour (AUR-21). Over it is `429` with `Retry-After`. |
| `LOGIN_PER_HOUR` | `20` | Sign-in attempts per client **IP**. The portal owns the real lockout; this stops us amplifying it. |
| `DOCTOR_PER_HOUR` | `30` | `/doctor` calls per client IP. It answers unverified callers on purpose, and `?fresh=1` costs a portal call. |
| `DATABASE_URL` | *(none — history off)* | Postgres for conversations, messages and feedback. Unset is a supported state: `/doctor` reports it, `/health` stays up, and chat falls back to the history the client sends. On Railway it is `${{Postgres.DATABASE_URL}}`, which resolves to the private network, so the database is never publicly reachable. Schema: [`schema.md`](schema.md). |

**Unbrander** (all optional while `UNBRANDER_ENABLED` is false; uploads still queue
whenever `DATABASE_URL` is set):

| Variable | Default | What it does |
|---|---|---|
| `UNBRANDER_ENABLED` | `false` | Starts the job worker. Off by default so a deploy never starts model spend. When true, the service **refuses to boot** unless `DATABASE_URL`, `OPENROUTER_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON` and the three `DRIVE_*` ids are set and OCR can run. |
| `UNBRANDER_DRY_RUN` | `true` | Files under `DRIVE_TEST_ROOT_FOLDER_ID`, never the real tree. |
| `UNBRANDER_DATA_DIR` | `.local/unbrander` | Uploads and cleaned outputs. On Railway, a volume mount path such as `/data/unbrander`: the container's own disk is lost on every deploy. |
| `UNBRANDER_RETENTION_DAYS` | `30` | Volume files are deleted this long after a job ends. |
| `UNBRANDER_MAX_FILE_MB` · `_MAX_PAGES` | `150` · `60` | Upload limits. The admin app reads them from `GET /admin/unbrander/limits`, so this is the only place to change them. One upload is held in memory at a time: check the host's memory before raising the size. |
| `UNBRANDER_DOCS_PER_DAY` | `30` | Documents started per UTC day; past it, jobs wait. |
| `UNBRANDER_DOC_TIMEOUT_MIN` | `10` | One document's budget; over it, the document fails. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | *(none)* | The service account key, the whole JSON on one line. Secret: a Railway variable, never a file on the volume. |
| `DRIVE_SHARED_DRIVE_ID` · `DRIVE_ROOT_FOLDER_ID` · `DRIVE_TEST_ROOT_FOLDER_ID` | *(none)* | The "Aura Agent" Shared Drive and its `Unbranded` and `Test` folders; the ids are in `.env.example`. |

The service account must be a **Content manager** member of the Shared Drive, and the
drive must allow people outside the organisation (a service account counts as outside).
Check it can write with `scripts/check_drive.py`.

Two things are deliberately **not** settings: the `aiindex` cache window
(`ExecApiProjectRepo.TTL_S`, 5 minutes) and the result caps in `tools.py`
(`MAX_RESULTS`, `MAX_COMPARE`). They are tuning decisions with reasons written
next to them, not per-environment knobs.

**The rate-limit counters are in memory, per process.** A second replica doubles
every ceiling above, because neither knows about the other's count. That is the
whole cost of not running Redis for twenty realtors; revisit it the day a second
replica exists, not before.

**The IP-keyed ceilings assume exactly one trusted hop in front of the service.**
Railway's edge appends the real peer to whatever `X-Forwarded-For` arrived, so
`client_ip` reads the **last** entry, not the first — the first is whatever the
caller wrote, and keying on it let a rotated header buy a fresh allowance every
request. Two things follow: **never expose the container directly** (with no
proxy appending, the whole header is caller-controlled again), and **if a second
proxy is ever put in the path, `client_ip` has to count hops** rather than take
the last entry.

### 2.1 Changing the model or the provider (AUR-86, AUR-10)

The model is a config string and nothing else — no rebuild, no code change, no
redeploy of anything but the variable.

```bash
railway variables --service api --set LLM_MODEL=anthropic/claude-sonnet-4.5
```

Any model id [OpenRouter](https://openrouter.ai/models) serves works, but it
**must support tool calling** — Aura answers by calling `search_projects`, not
by knowing anything. A model without tools returns confident prose about
projects that do not exist, which is the one failure mode this system exists to
prevent.

Changing provider entirely means changing `OPENROUTER_API_KEY` and the base URL
in `app/capabilities/chat/adapters/agent_pydantic.py`. Everything above that file is unaffected:
the runtime is a port.

**Verify after changing**, in this order — the first two need no realtor token:

```bash
curl -s $BASE/health
```

`model` must not be `false`. Then, with a token:

```bash
curl -s -H "Authorization: Bearer $TOK" $BASE/doctor | python3 -m json.tool
```

Then ask a question that must use a tool, and confirm the `tool` frame appears
before any `text`:

```bash
curl -sN -X POST $BASE/chat -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{"question":"detached under $1M in Brampton"}'
```

A stream that goes straight from `start` to `text` is a model that is not
calling tools — change it back. Finish with the benchmark
(`.venv/bin/python -m app.capabilities.chat.bench`), because a model can call tools correctly and
still be worse at reading the results.

---

## 3. Running it locally

**The quick way:** `aura-agent/bin/setup` once, then `aura-agent/bin/dev`. It checks the
machine (Node, the venv, tesseract, the admin app's packages, Postgres and its database,
free ports), then runs shape B below with the admin app beside it: portal stand-in on
:4599, api on :8001, admin app on :5173, one terminal, Ctrl-C stops all three.
`--worker` turns the job worker on; it calls paid models. The rest of this section is
what it does by hand, and the real-portal shape it does not cover.

Two shapes, and which one you want depends on whether you have a Portal ID and
an OpenRouter key.

### A. Real everything

Your existing `.env`, a real Portal ID, and the api against the live portal.
Real projects, real model answers, real feedback.

```bash
cd aura-agent/api && .venv/bin/uvicorn app.main:app --reload      # :8000
```

Chat has no UI while it is parked, so ask through the CLI:

```bash
cd aura-agent/api && .venv/bin/aura login && .venv/bin/aura --dev
```

For the admin app against the same api, run it beside it with
`VITE_AURA_BASE=http://localhost:8000` and sign in with an admin Portal ID.
`ALLOWED_ORIGINS` already defaults to `http://localhost:5173`, so CORS needs no
change.

Without `OPENROUTER_API_KEY` in `.env`, `/chat` answers
`the model is not configured`.

### Conversation history, locally

`DATABASE_URL` is optional. Without it everything works except history — which is
the point of making persistence the feature that degrades.

To exercise it, a local Postgres is enough:

```bash
createdb aura_chat_dev
```

```bash
cd aura-agent/api && DATABASE_URL=postgresql://$USER@localhost/aura_chat_dev .venv/bin/uvicorn app.main:app --reload
```

Name the user in the DSN. Omitted, asyncpg falls back to the process owner,
which under a launcher may not be you — the failure is
`role "root" does not exist` behind a `503` that reads exactly like a database
that is down.

The schema is applied on startup, so there is no migration step. Two scripts
prove the store against a real database — they are not pytest, because the suite
must never need one:

```bash
DATABASE_URL=postgresql://localhost/aura_chat_dev .venv/bin/python scripts/check_store.py
```

```bash
DATABASE_URL=postgresql://localhost/aura_chat_dev .venv/bin/python scripts/check_chat_persistence.py
```

Railway's own database is on the private network and **not reachable from a
laptop**, which is deliberate. Use a local one for development.

### The fully-local stack cannot read project data, and that is expected

`aura-agent/bin/dev` needs no real credentials: the portal stand-in
(`aura-agent/portal/dev/serve.mjs`, with `authshim.mjs`) answers `login` and
`session` locally, and **every other action is proxied to the live
deployment**, which has never heard of a dev token. So Chat's `aiindex` read is
refused with `login required`.

That is the harness, not a defect. It is fine for the admin app, Unbrander and
the organization profile, none of which read the portal's data actions. For
Chat answers over real projects, use **A. Real everything** above with a real
Portal ID.

### Unbrander, locally

`scripts/setup.sh` makes the venv, installs tesseract and checks OCR. With
`DATABASE_URL` set, uploads work and wait in `RECEIVED`; to run them, also set
`OPENROUTER_API_KEY` and `UNBRANDER_ENABLED=true`. Jobs then stop at `UNBRANDED`, ready
to review and download. Filing needs the key and the `DRIVE_*` ids as well; dry run
stays on, so filed output lands in the Drive `Test` folder. Each document costs model calls
(about $0.07 for the 8-page sample in [model-check.md](../Unbrander/model-check.md)).

The admin app runs beside it: start `aura` with `localhost:5173` in `ALLOWED_ORIGINS`,
then `cd aura-agent/ui/admin && VITE_AURA_BASE=http://localhost:8000 npm run dev` (the
`agent-ui` entry in `.claude/launch.json` points at the `aura` entry's port 8001).
Sign in with an admin portal login. Commands and rules: `aura-agent/ui/admin/AGENTS.md`.

### B. No portal account, no API key

What `aura-agent/bin/dev` runs, by hand: the portal stand-in for a fixture
sign-in, and the api pointed at it.

```bash
node aura-agent/portal/dev/serve.mjs                          # :4599
```

```bash
cd aura-agent/api && TOKEN_SECRET=dev-token-secret-not-a-real-key \
  EXEC_URL=http://localhost:4599/api .venv/bin/uvicorn app.main:app --port 8000
```

**Both env vars are load-bearing.** The stand-in mints tokens with that dev
secret, so `TOKEN_SECRET` has to match it — and `EXEC_URL` has to point back at
the stand-in, because `verify()` asks the portal whether the account still lives.
Left at the real deployment it is asked about a locally-minted token, says no,
and every request 401s with nothing in the log explaining why.

Fixture users are in
[`aura-agent/portal/dev/authshim.mjs`](../../../portal/dev/authshim.mjs) —
`harvinder` / `Summer2026`.

### Two traps, each of which fails quietly

1. **A stale server holds the port and the new one dies into a log nobody
   reads.** `EADDRINUSE` from a backgrounded `serve.mjs` looks exactly like
   everything working, because the old server is still answering.

   ```bash
   lsof -nP -iTCP:4599 -sTCP:LISTEN
   ```

2. **An old `uvicorn` on :8000 serves the routes it had when it started.** A
   route added since is a 404 that reads like a client bug. Same check, port
   8000.

---

## 4. Deploying

Railway, from the `Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

1. Set `TOKEN_SECRET` and `EXEC_URL` in Railway's variables. The service starts
   without them and then refuses every request — `/doctor` names which is
   missing, `/health` deliberately does not.
1b. Set `ALLOWED_ORIGINS` to the admin app's origin. Without it the admin app
   fails in the browser with a CORS error and a green `/health` — the request never
   reaches the service, so nothing here records that it happened.
2. **Set a usage limit on day one.** Railway has no spend cap by default; this
   is a listed risk in [`architecture.md`](architecture.md) §7.
2b. Set `DATABASE_URL` to `${{Postgres.DATABASE_URL}}`. Without it the service
   runs fine and silently keeps no history — `/doctor` reports
   `conversation_store: not wired yet` and that is the only sign.

2c. **Unbrander**, only when turning the worker on: set
   `RAILPACK_DEPLOY_APT_PACKAGES=tesseract-ocr` (OCR; `deploy.sh` warns when it is
   missing), attach a volume and point `UNBRANDER_DATA_DIR` into it, then
   `UNBRANDER_ENABLED=true`. Filing in Drive is optional: set the key and all three
   `DRIVE_*` ids, or none. A missing piece stops the boot with its name in the log,
   rather than failing the first PDF. `/doctor` then shows `ocr`, `job_store` and
   `unbrander_worker` ok, and `drive` ok or "not set up".
3. `GET /health` should answer `{"status":"ok","ok":true}` from the internet.
4. `GET /doctor` with a real token is the actual readiness check — it proves the
   portal accepts our auth *and* that project data comes back.
5. **Prove the host does not buffer.** The chat is nothing but a stream, and a
   buffering proxy turns it into a five-second blank followed by a wall of text
   — with the same 200 as a healthy one, so nothing else catches it:

   ```bash
   curl -N -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
     -d '{"question":"cheapest project"}' https://<service>/chat
   ```

   Events must appear one at a time. This is why Netlify's redirect proxy was
   rejected as a way to make the service same-origin: it buffers, and long
   responses 502.
6. **The admin app** (`aura-agent/ui/admin/`) — its deployment is parked for now.
   When it ships, it is its own Netlify site: base directory
   `aura-agent/ui/admin`, build and publish from its `netlify.toml`, and `VITE_AURA_BASE`
   set to the service's URL. Add the site's origin to the service's
   `ALLOWED_ORIGINS`. The service URL is also in `netlify.toml`'s CSP
   `connect-src`: when the service moves, change it there, in `VITE_AURA_BASE`, and
   redeploy the site. Check: sign in as an admin and see the job list; a realtor
   login is refused.

---

## 4.1 Restarting, rolling back, and what a redeploy costs (AUR-91)

```bash
railway redeploy --service api
```

A restart costs **the caches, and nothing else**. Conversations, messages and
feedback are in Postgres and survive. What is thrown away:

| Lost on restart | Cost |
|---|---|
| The `aiindex` project cache (5 min TTL) | The first question after a restart is slow — one portal fetch |
| The auth liveness cache (60 s) | One extra portal call per realtor |
| **The rate-limit counters** | Everyone's hourly allowance resets. A restart is a way to un-throttle somebody, and also a way for a runaway client to get 60 more |

The schema is applied on every boot and is idempotent, so there is no migration
step and no order to get right.

**Rolling back** is Railway's deployment list — redeploy the previous build. The
only thing to check first is whether the rollback crosses a schema change:
`schema.sql` only ever adds, so an older build against a newer database is safe,
but an older build will not re-create a table a newer one added.

**Never touch the Apps Script side to fix Aura.** If the portal must be
republished, edit the **existing** deployment. "New deployment" mints a new id
and leaves this service's `EXEC_URL` calling an address that no longer
answers. See [`portal.md`](../../portal.md).

---

## 4.2 Logs, errors, and where to look (AUR-20, AUR-93)

Everything goes to **stdout**, which on Railway means
`railway logs --service api`. There is no log file and no audit table:
Railway already retains and searches this, and a second write on the answer path
would buy a retention problem of our own.

Deliberately: the log window is **bounded**. Anything that has to outlive it —
the feedback queue above all — belongs in Postgres, and does now.

Every line is `TIMESTAMP LEVEL logger message`, and every logger is under `aura`:

| Logger | Level | What it is |
|---|---|---|
| `aura.audit` | INFO | **One JSON line per question.** The audit trail. |
| `aura.feedback` | INFO | One JSON line per report |
| `aura.auth` | INFO | A refused request: the reason, the IP, the path. Never the token. |
| `aura.chat` | WARNING | The store was unreachable, or the answer stream failed |
| `aura.conversations` | WARNING | The store was unreachable behind a `503` |
| `uvicorn.access` | INFO | One line per request, with the status |

### The audit line

```json
{"rid":"37decfb14bb2","user":"priya","role":"realtor","mode":"realtor",
 "question":"detached under $1M in Brampton","conversation_id":"4e29f845-…",
 "tools":[{"t":"search_projects","n":6}],"tokens_in":1742,"tokens_out":210,
 "ms":3104,"status":"ok","error":null}
```

`status` is one of `ok`, `error`, or **`incomplete`** — the last meaning the
request was cancelled before the stream finished, usually a client that went away.
It is written in a `finally`, so a dropped connection still leaves a line.

**The question is in the line and the answer never is.** A question is
realtor-authored and cannot contain sheet data; an answer in Realtor Mode can
quote commission, and a hosting platform's log is not where that lives. Do not
add it without moving the store first.

### Starting from a complaint

Every response carries `X-Request-Id`, and it is the first thing to ask for.

```bash
railway logs --service api | grep 37decfb14bb2
```

Without one, `grep aura.audit | grep '"user":"priya"'` narrows it to one
realtor. `status` and `error` say what happened; `ms` says whether it was slow;
`tools` says whether the model even looked.

Common lines and what they mean:

| Line | Cause |
|---|---|
| `auth refused: token did not verify` | Expired session — or `TOKEN_SECRET` no longer matches the portal. `/doctor` tells the two apart. |
| `conversation store unavailable` | Postgres is down. Chat still answers; history does not. |
| `"status":"error","error":"PortalError: …"` | The portal refused or did not answer. Check `/doctor`. |
| `"status":"incomplete"` | The realtor left, or the connection dropped. Not an error. |
| `429` in the access log | The rate limit (§2). |

Pulling a day down for analysis:

```bash
railway logs --service api | grep 'aura.audit' | sed 's/.*aura.audit //' > audit-$(date +%F).jsonl
```

---

## 5. Rotating `TOKEN_SECRET`

The secret now lives in **two** managed stores, and they must agree byte for
byte. A mismatch is the worst failure mode in the system: every realtor gets
401 from Aura Chat while `/health` stays green and the portal itself keeps
working normally.

Rotation is therefore not atomic, and every existing token dies with the old
value. Do it when nobody is mid-conversation:

1. Apps Script → *Project Settings → Script Properties* → set `TOKEN_SECRET`.
2. Railway → variables → set the identical value → redeploy.
3. `GET /doctor` with a **freshly minted** token (§1). `token_verification`
   must say `verified as <user>`.
4. Every realtor must sign in again. Tokens minted under the old secret no
   longer verify anywhere.

If step 3 reports *"the portal accepts this token but this service cannot
verify it"*, the two values differ — usually a trailing newline or a partial
paste.
