# Aura Chat — operations

Everything environmental: getting a token, what each setting does, deploying,
and rotating the one secret whose failure is invisible. Referenced from
[`../../AGENTS.md`](../../AGENTS.md).

---

## 1. Getting a portal token

`/doctor`, `/me` and every tool call need a realtor's own session token — this
service holds no credential of its own, so there is no way around having one.
Two ways to get it.

**Mint one against the portal.** `login` is a public action, so this needs only
a real Portal ID and password:

```bash
EXEC=$(grep -o "https://script.google.com/[^']*" dev/config.mjs | head -1)
curl -sL "$EXEC" -H 'Content-Type: text/plain;charset=utf-8' \
  -d '{"action":"login","username":"YOUR_ID","password":"YOUR_PASSWORD"}'
```

Answers `{"ok":true,"name":…,"role":"realtor","token":"…"}`.

Two details that are the difference between JSON and a wall of Google HTML.
`-L`, because Apps Script answers a POST with a 302 and serves the body from
`script.googleusercontent.com`. And **no `-X POST`** — `-d` already makes it a
POST, while `-X` pins the method across the redirect too, and that second hop
only answers GET. With `-X POST` you get a 405 and an HTML error page.

**Or lift it from the installed app.** In the PWA's devtools console:

```js
sessionStorage.getItem('ak_token') || localStorage.getItem('ak_token')
```

`sessionStorage` is where it lands when "Remember me" was unchecked.

Then:

```bash
TOK='<paste>'
curl -s -H "Authorization: Bearer $TOK" localhost:8000/doctor | python3 -m json.tool
```

A token is valid for 7 days from issue and the portal slides it on every app
launch. It carries the realtor's role, so an admin token and a realtor token
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
| `EXEC_URL` | *(none)* | The deployed Apps Script web app. Must equal `EXEC` in `dev/config.mjs`. |
| `EXEC_TIMEOUT_S` | `30.0` | Per-request timeout against the portal. Cold index builds are slow; see [`../portal.md`](../portal.md) §3.6. |
| `SESSION_MS` | `604800000` (7 days) | Token lifetime. **Must match `SESSION_MS` in `Core.js`** — longer here keeps honouring tokens the portal has retired. |
| `ALLOWED_ORIGINS` | `http://localhost:4600,http://localhost:4599` | Comma-separated CORS allowlist. The PWA's origin **must** be in here or the browser blocks the chat before the request leaves the phone. Never `*`: a wildcard lets any page a realtor visits spend their token. |
| `ALLOWED_ORIGIN_REGEX` | *(empty)* | Only for Netlify deploy previews, which get a random subdomain per draft deploy and so cannot be named in the list. A standing hole in the allowlist — set it while testing previews, unset it after. |
| `OPENROUTER_API_KEY` | *(none)* | Phase 3. |
| `LLM_MODEL` | `google/gemini-2.5-flash` | A model swap is this string. See §2.1. |
| `LLM_MAX_TOKENS` | `1500` | A ceiling on the answer, not a target. Left unset, providers advertise their whole context as `max_tokens` — 65k on Gemini Flash — which OpenRouter bills against up front, so a request can be refused for lack of credit to cover an answer nobody wanted. |
| `CHAT_PER_HOUR` | `60` | Questions per **user** per hour (AUR-21). Over it is `429` with `Retry-After`. |
| `LOGIN_PER_HOUR` | `20` | Sign-in attempts per client **IP**. The portal owns the real lockout; this stops us amplifying it. |
| `DOCTOR_PER_HOUR` | `30` | `/doctor` calls per client IP. It answers unverified callers on purpose, and `?fresh=1` costs a portal call. |
| `DATABASE_URL` | *(none — history off)* | Postgres for conversations, messages and feedback. Unset is a supported state: `/doctor` reports it, `/health` stays up, and chat falls back to the history the client sends. On Railway it is `${{Postgres.DATABASE_URL}}`, which resolves to the private network, so the database is never publicly reachable. Schema: [`schema.md`](schema.md). |

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
railway variables --service aura-chat --set LLM_MODEL=anthropic/claude-sonnet-4.5
```

Any model id [OpenRouter](https://openrouter.ai/models) serves works, but it
**must support tool calling** — Aura answers by calling `search_projects`, not
by knowing anything. A model without tools returns confident prose about
projects that do not exist, which is the one failure mode this system exists to
prevent.

Changing provider entirely means changing `OPENROUTER_API_KEY` and the base URL
in `app/adapters/agent_pydantic.py`. Everything above that file is unaffected:
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
(`.venv/bin/python -m app.bench`), because a model can call tools correctly and
still be worse at reading the results.

---

## 3. Running it locally

Two shapes, and which one you want depends on whether you have a Portal ID and
an OpenRouter key.

### A. Real everything

Two processes and your existing `.env`. Real projects, real model answers, real
feedback.

```bash
cd aura-chat && .venv/bin/uvicorn app.main:app --reload      # :8000
```

```bash
node dev/build.mjs --serve                                   # :4600, real portal
```

Then open `http://localhost:4600` and sign in with a real Portal ID.

`AURA_BASE` is the only variable you have to set, and only to turn the chat
button on:

```bash
AURA_BASE=http://localhost:8000 node dev/build.mjs --serve
```

Everything else is already the default. The bundle talks to the live deployment
because that URL is the fallback in
[`../../dev/config.mjs`](../../dev/config.mjs) — `AK_EXEC` exists to point at a
*different* deployment, not at the normal one. Reading it from the browser works
because the Apps Script web app answers with `Access-Control-Allow-Origin: *`,
and `ALLOWED_ORIGINS` already lists `localhost:4600`, so CORS needs no change.

Without `OPENROUTER_API_KEY` in `.env` the screen loads and `/chat` answers
`the model is not configured`.

### Conversation history, locally

`DATABASE_URL` is optional. Without it everything works except history — which is
the point of making persistence the feature that degrades.

To exercise it, a local Postgres is enough:

```bash
createdb aura_chat_dev
```

```bash
cd aura-chat && DATABASE_URL=postgresql://$USER@localhost/aura_chat_dev .venv/bin/uvicorn app.main:app --reload
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

### The fully-local stack signs you out, and that is expected

`.claude/launch.json` has a `portal` + `aura` + `bundle-aura` trio that needs no
real credentials: `dev/authshim.mjs` answers `login` and `session` locally with
the real `Core.js`, and **every other action is proxied to the live
deployment**, which has never heard of a dev token. So the first data screen
returns `login required`, `isAuthErr` reads that as a dead session, and you are
back at the gate a second after signing in.

That is the harness, not a defect. It is fine for the chat, the history panel
and the reports screen, none of which touch the portal's data actions. For
anything that does, use **A. Real everything** above with a real Portal ID.

### B. No portal account, no API key

For UI work. Adds `dev/serve.mjs` for a fixture sign-in, and needs a stub for
`/chat` since there is no model.

```bash
node dev/serve.mjs                                            # :4599
```

```bash
cd aura-chat && TOKEN_SECRET=dev-token-secret-not-a-real-key \
  EXEC_URL=http://localhost:4599/api .venv/bin/uvicorn app.main:app --port 8000
```

**Both env vars are load-bearing.** The harness mints tokens with that dev
secret, so `TOKEN_SECRET` has to match it — and `EXEC_URL` has to point back at
the harness, because `verify()` asks the portal whether the account still lives.
Left at the real deployment it is asked about a locally-minted token, says no,
and every request 401s with nothing in the log explaining why.

Fixture users are in [`../../dev/authshim.mjs`](../../dev/authshim.mjs) —
`harvinder` / `Summer2026`.

**You cannot reach the chat through the gate this way.** `dev/serve.mjs` answers
only `login` and `session` locally and proxies everything else to the live
deployment, which refuses a dev token — so `verifySession` signs you straight
back out. Set the token by hand in the console instead:

```js
TOKEN = 'paste a token from dev/serve.mjs login';
document.getElementById('gate').hidden = true;
document.getElementById('aura').hidden = false;
document.body.classList.add('chat');
auraPaint();
```

### Three traps, each of which fails quietly

1. **The service worker caches `index.html`.** Change `AURA_BASE` or `AK_EXEC`
   and the old value survives a reload, so the chat talks to a port nothing is
   listening on. Clear it and reload twice:

   ```js
   navigator.serviceWorker.getRegistrations().then(r => r.forEach(x => x.unregister()))
   ```

2. **A stale server holds the port and the new one dies into a log nobody
   reads.** `EADDRINUSE` from a backgrounded `build.mjs --serve` looks exactly
   like everything working, because the old server is still answering.

   ```bash
   lsof -nP -iTCP:4600 -sTCP:LISTEN
   ```

3. **An old `uvicorn` on :8000 serves the routes it had when it started.** A
   route added since is a 404 that reads like a client bug. Same check, port
   8000.

---

## 4. Deploying

Railway, from the `Procfile`: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

1. Set `TOKEN_SECRET` and `EXEC_URL` in Railway's variables. The service starts
   without them and then refuses every request — `/doctor` names which is
   missing, `/health` deliberately does not.
1b. Set `ALLOWED_ORIGINS` to the PWA's origin. Without it the chat screen fails
   in the browser with a CORS error and a green `/health` — the request never
   reaches the service, so nothing here records that it happened.
2. **Set a usage limit on day one.** Railway has no spend cap by default; this
   is a listed risk in [`architecture.md`](architecture.md) §7.
2b. Set `DATABASE_URL` to `${{Postgres.DATABASE_URL}}`. Without it the service
   runs fine and silently keeps no history — `/doctor` reports
   `conversation_store: not wired yet` and that is the only sign.

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
6. Rebuild and redeploy the PWA with `AURA_BASE` pointing at the service —
   `AURA_BASE=https://<service> node dev/deploy.mjs --prod`. Until that is set,
   the bundle ships without the chat button by design; see
   [`../portal.md`](../portal.md). The Apps Script-hosted copy never gets it:
   its pages come from a `googleusercontent.com` subdomain whose hash varies, so
   the origin cannot be allowlisted, and Apps Script cannot stream anyway.

---

## 4.1 Restarting, rolling back, and what a redeploy costs (AUR-91)

```bash
railway redeploy --service aura-chat
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
and leaves every installed phone — and this service's `EXEC_URL` — calling an
address that no longer answers. See [`../portal.md`](../portal.md).

---

## 4.2 Logs, errors, and where to look (AUR-20, AUR-93)

Everything goes to **stdout**, which on Railway means
`railway logs --service aura-chat`. There is no log file and no audit table:
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
request was cancelled before the stream finished, usually a backgrounded phone.
It is written in a `finally`, so a dropped connection still leaves a line.

**The question is in the line and the answer never is.** A question is
realtor-authored and cannot contain sheet data; an answer in Realtor Mode can
quote commission, and a hosting platform's log is not where that lives. Do not
add it without moving the store first.

### Starting from a complaint

Every response carries `X-Request-Id`, and it is the first thing to ask for.

```bash
railway logs --service aura-chat | grep 37decfb14bb2
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
railway logs --service aura-chat | grep 'aura.audit' | sed 's/.*aura.audit //' > audit-$(date +%F).jsonl
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
