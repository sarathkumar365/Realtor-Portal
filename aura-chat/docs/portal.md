# The Realtor Portal (upstream)

The Apps Script web app that Aura Chat reads its data and identity from, and the
installable PWA that realtors actually open. Aura Chat depends on this; it does
not change it. Read [`../AGENTS.md`](../AGENTS.md) first — this file is only for
work that touches the portal itself.

---

## 1. What this is

The internal mobile toolkit for **Aura Key Realty**, a Greater-Toronto-Area
brokerage of roughly twenty realtors. New-build projects by city, builder and
concierge contacts, school rankings, LTB and crime lookups, a carrying-cost
calculator, the team leaderboard, each realtor's own deals, and the onboarding
bootcamp.

**One codebase, two hosts.**

| Host | What it serves | Entry point |
|---|---|---|
| Google Apps Script web app | The HTML app *and* the JSON API | `doGet` / `doPost` / `app()` in `Core.js` |
| Netlify (static) | The installable PWA, generated from the same HTML | `www/`, built by `dev/build.mjs` |

The PWA is **derived**, never hand-edited. `App.html` + `Styles.html` +
`Script.html` are the single source of truth for both hosts. The only
behavioural difference between them is `window.AK_EXEC`: when it is set (the
static bundle), `call()` in `Script.html` uses `fetch` against the Apps Script
`/exec` URL; when it is not (Apps Script), it uses the `google.script.run`
bridge.

There is no database, no framework, no bundler for the app, and no npm
dependencies. Data lives in three Google Sheets, read through `Sheets.js`.

---

## 2. Repo map

| Path | What it is |
|---|---|
| `Core.js` | Config, token auth, cache layer, the `app(action, params)` dispatch table, `doGet`/`doPost` |
| `Sheets.js` | Generic tab readers, the project/directory readers, login |
| `Team.js` | Team screens: home, leaderboard, deals, bootcamp |
| `External.js` | Proxied third-party APIs: LTB, crime, schools, basement registration |
| `Ai.js` | The `aiindex` action — the whole cross-city project set in one payload, for Aura Chat |
| `Audit.js` | Editor-only, read-only schema diagnostics. Nothing routed, nothing written |
| `App.html` | Page shell + the sign-in gate markup |
| `Styles.html` | All CSS, one `<style>` element |
| `Script.html` | All client JS, one `<script>` element (~2,100 lines) |
| `appsscript.json` | Apps Script manifest (V8, executes as owner, anonymous access) |
| `.claspignore` | What `clasp push` must **never** upload — see §3.2 |
| `dev/*.mjs` | Local harness, PWA build, deploy, pre-push verification (Node, ESM) |
| `assets/` | Icons and gate artwork consumed by the build |
| `www/`, `.netlify/` | **Generated. Gitignored. Never edit** |
| `aura-chat/` | Separate Python 3.12 / FastAPI service (live in production) — see §7 |
| `docs/worklog.md` | **Why** things are the way they are. Append on every substantive change — see §7 |
| `docs/` | Architecture decisions and investigations |
| `design_handoff_aura_key/` | Design references (HTML prototypes), not production code |

---

## 3. Sharp edges

These are the ways this project breaks production. Each one has already
happened at least once.

### 3.1 Apps Script has one global scope

`Core.js`, `Sheets.js`, `Team.js`, `External.js`, `Ai.js` and `Audit.js` are
concatenated into a single scope at runtime. Load order does not matter, but
**a duplicate top-level name silently wins or loses**, and a syntax error in any
one file breaks every request. `dev/verify.mjs` loads all of them together for
exactly this reason.

### 3.2 `clasp` pushes everything you do not exclude

`.clasp.json` sets `rootDir: ""` and `skipSubdirectories: false`, so every
`.js` / `.html` / `.json` in the repo is a push candidate. `www/app.js` in the
server's global scope throws on `document` before `doGet` can answer and 500s
every request, login included.

`.claspignore` is the guard, and `dev/verify.mjs` inverts the rule: **anything
in the repo root that is not a known server file must be ignored explicitly**.
Adding a new folder to the root therefore fails verification the day it appears
— fix it by listing the folder in `.claspignore`, or, if it really is server
code, by adding it to `SERVER_FILES` in `dev/verify.mjs`.

### 3.3 The deployment id is the app's lifeline

The installed PWA carries the `/exec` URL in its bundle and cannot discover a
new one. Publishing through **"New deployment"** mints a fresh id and retires
the old one, and every phone dies. **Always publish by editing the existing
deployment.** If the id ever does change, update `EXEC` in `dev/config.mjs`
*and* `EXEC_URL` in `aura-chat/.env`, then rebuild and redeploy the bundle.

### 3.4 `www/` is generated and gitignored

`netlify deploy --dir=www` ships whatever happens to be on disk, and the
service worker is cache-first — a stale shell pins itself on every installed
phone until the next deploy. **Deploy only through `dev/deploy.mjs`**, which
rebuilds immediately before handing the directory to Netlify.

### 3.5 Secrets live in Script Properties and fail closed

`TOKEN_SECRET`, `PASSWORD_PEPPER` and `ADMIN_PASSCODE` are read from
*Project Settings → Script Properties*. They are never in the repo, and the code
throws rather than falling back to a default. Set them in any new Apps Script
project **before** deploying, or every login fails.

### 3.6 Cold reads are genuinely slow

`getHome_ → getFocus_ → getSearchIndex_` walks ~60 city tabs and measured
51–68s cold. Hence `CACHE_TTL = 21600` (the `CacheService` maximum), the
`warmCache()` time-trigger, the chunked cache in `Core.js` (payloads over 45k
chars are split across keys), and per-call abort budgets on the client (15s
when a cached copy exists, 75s when it does not). Do not shorten a client
timeout without checking whether that call has a fallback.

---

## 4. Commands

```bash
node dev/verify.mjs                 # pre-push checks — must pass before clasp push
clasp push                          # publish server + HTML to Apps Script
clasp status                        # list exactly what a push would upload

node dev/serve.mjs                  # dev harness on :4599 (App.html + a google.script.run shim)
node dev/build.mjs                  # build www/
node dev/build.mjs --serve          # build, then serve www/ on :4600, rebuilding per request
AK_EXEC=http://localhost:4599/api node dev/build.mjs --serve   # bundle against the local harness

node dev/deploy.mjs                 # draft deploy (preview URL, nobody's install)
node dev/deploy.mjs --prod          # production
```

`AK_EXEC=<url>` points any of them at a different deployment.
The two dev servers are also registered in `.claude/launch.json` as `portal`
and `bundle`.

---

## 5. Architecture

### 5.1 Server

Everything is one action on one endpoint: `app(action, params)` in `Core.js`.
`doGet` renders the template; `doPost` and `google.script.run` both land in
`app()`.

Access control is our own token layer, because the web app is deliberately
**anonymous** — realtors may have no Google account, and the sign-in gate has to
be publicly reachable:

- `PUBLIC_ACTIONS` = `login`, `session`. They mint or refresh a token, and are
  POST-only so a password or token never lands in a query string or the
  execution log.
- Everything else goes through `requireAuth_`, which verifies the HMAC token and
  hands handlers the already-verified claims as `p.__tok`.
- Role checks (`p.__tok.role === 'admin'`) happen **on the server**. The client
  hiding a button is presentation, never protection.

Token shape: `base64url(user|role|credGen|issuedMillis) . base64url(HMAC-SHA256(raw, TOKEN_SECRET))`.
The timestamp is read **from the end**, so an older three-field token still
parses.

### 5.2 Client

`Script.html` is one script, no modules. `NAV` declares the drawer; `LOAD` maps
a route to its loader; `go()` sets the hash and `route()` renders. A screen is a
`NAV` entry, a `SUB` description, a `LOAD` entry, and a loader function.

- `call(action, params)` attaches the session token automatically. Never attach
  it at a call site.
- `isAuthErr` / `sessionLost()` re-gate centrally. An "admin only" refusal is
  *not* an auth error and must not sign the user out.
- Anything interpolated into HTML goes through `esc()`; any URL through
  `safeUrl()`.
- Screens render a skeleton first, then data, then an error state — a throw in
  `route()` must never leave placeholder cards up forever.

### 5.3 PWA build

`dev/build.mjs` unwraps `Styles.html` into `app.css` and `Script.html` into
`app.js`, writes an `index.html` that sets `window.AK_EXEC` before `app.js`
loads, copies icons and gate artwork, and generates `sw.js` with a
content-hashed cache name. The shell is precached as one unit: a partial
install would work online and be a blank page offline.

### 5.4 Data

Three spreadsheets, keyed in `SHEETS` (`main`, `deals`, `onboarding`). City and
school tabs put **headers on row 2, data from row 3** (`HEADER_ROW`,
`DATA_START`). Tab access is allow-listed; readers cache by tab and header row.

---

## 6. Conventions

**Style — match the file you are in.**

- Server files and `Script.html`: ES5-flavoured house style, `var` and
  `function`, no arrow functions, no build step. `dev/*.mjs` is modern Node ESM
  (`const`, arrows, top-level `await`).
- A trailing underscore (`getHome_`, `requireAuth_`) marks a private helper.
  Apps Script will not expose those to `google.script.run`, so anything the
  client calls directly must **not** have one.
- CSS: tokens in `:root` at the top of `Styles.html`, `rem` for type and
  spacing. Inputs carry a 16px floor — below it, iOS zooms on focus.

**Comments explain why, not what.** This codebase's comments carry the reason a
line exists, the failure it prevents, and what was measured. Keep that. A
comment restating the code is worse than none.

**Commit messages** follow `type: imperative summary` (`feat`, `fix`, `perf`,
`security`, `chore`, `style`) with a body that explains the failure, the
mechanism, and how it was verified. Read `git log` before writing one — the bar
is high and deliberate.

**Do not:**

- edit `www/`, `.netlify/`, or anything else generated
- hand-copy a fix into both `Script.html` and `www/app.js` — rebuild instead
- put a secret, a sheet id you invented, or a hardcoded token in the repo
- add an npm dependency to the app (`dev/` is dependency-free Node too)
- widen `PUBLIC_ACTIONS` without a deliberate reason

---

## 7. Before you push

1. `node dev/verify.mjs` — all checks pass.
2. `clasp status` — nothing unexpected in the upload list.
3. Server change → `clasp push`, then publish by **editing the existing
   deployment**.
4. Client change → `node dev/deploy.mjs --prod` as well, or installed phones
   keep the old shell.
5. Substantive change → `docs/worklog.md` has an entry for it (§7).
