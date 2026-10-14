# The Realtor Portal back end (upstream)

The Apps Script web app that Aura Agent reads its identity and Chat's project
data from. Aura Agent depends on it; it does not change it. Read
[`AGENTS.md`](../AGENTS.md) first — this file is only for work that
touches the portal back end itself.

---

## 1. What this is

The JSON back end of the old internal toolkit for **Aura Key Realty**, a
Greater-Toronto-Area brokerage of roughly twenty realtors. It reads three
Google Sheets and answers one `POST {action, auth}` endpoint.

The realtor PWA that used to sit on top of it has been retired — nobody used
it — so the repo no longer carries any of its HTML, build or deploy tooling.
The deployed web app itself **keeps running unchanged**: nothing has been
pushed to it since, and Aura Agent still calls it.

Its source now lives in [`portal/`](../portal/), and `clasp` runs
from that folder.

It is **slated for replacement**: the plan is for the agent to hold its own
users and login, and to read the Sheet with its Google service account (see
[roadmap.md](feature/aura-chat/roadmap.md)). Until then, treat it as a
dependency to keep alive, not a codebase to grow.

There is no database, no framework, no bundler and no npm dependencies. Data
lives in three Google Sheets, read through `Sheets.js`.

---

## 2. What Aura Agent calls

| Action | Who calls it | What it does |
|---|---|---|
| `login` | the admin app's sign-in, through the api's `/login` | Checks a realtor's credentials and mints the HMAC session token |
| `session` | the api's token check (`auth_portal_hmac.py`) and `/doctor` | Confirms the account behind a locally valid token still lives, and re-issues the token |
| `aiindex` | Chat's project repository | The whole cross-city project set in one payload, token-gated and read-only. Added for Aura Chat in Phase 2 (`Ai.js`) |

The token these return is the one Aura Agent verifies itself with the same
`TOKEN_SECRET` (invariant 1), and the caller's own token is what Aura Agent
sends back on every read (invariant 2).

---

## 3. Files

| Path | What it is |
|---|---|
| `portal/Core.js` | Config, token auth, cache layer, the `app(action, params)` dispatch table, `doGet`/`doPost` |
| `portal/Sheets.js` | Generic tab readers, the project/directory readers, login |
| `portal/Team.js` | Team data: home, leaderboard, deals, bootcamp |
| `portal/External.js` | Proxied third-party APIs: LTB, crime, schools, basement registration |
| `portal/Tax.js` | Ontario property tax rates, read from the main spreadsheet |
| `portal/Ai.js` | The `aiindex` action, for Aura Chat |
| `portal/Audit.js` | Editor-only, read-only schema diagnostics. Nothing routed, nothing written |
| `portal/appsscript.json` | Apps Script manifest (V8, executes as owner, anonymous access) |
| `portal/.clasp.json` | The Apps Script project id; `rootDir: ""` means this folder |
| `portal/.claspignore` | What `clasp push` must **never** upload — see §4.2 |
| `portal/dev/verify.mjs` | Pre-push verification of the server files (Node, ESM) |
| `portal/dev/serve.mjs` | API-only local stand-in on :4599, used by `bin/dev` |
| `portal/dev/authshim.mjs` | Fixture `login` and `session` answers for the stand-in |
| `portal/dev/config.mjs` | `EXEC` — the deployed web app's `/exec` URL |

---

## 4. Sharp edges

These are the ways this back end breaks production. Each one has already
happened at least once.

### 4.1 Apps Script has one global scope

`Core.js`, `Sheets.js`, `Team.js`, `External.js`, `Ai.js`, `Tax.js` and
`Audit.js` are concatenated into a single scope at runtime. Load order does not
matter, but **a duplicate top-level name silently wins or loses**, and a syntax
error in any one file breaks every request. `dev/verify.mjs` loads the routed
server files together for exactly this reason.

### 4.2 `clasp` pushes everything you do not exclude — verify first

`.clasp.json` sets `rootDir: ""` and `skipSubdirectories: false`, so every
`.js` / `.html` / `.json` under `portal/` is a push candidate. A
browser or Node file in the server's global scope throws before `doGet` can
answer and 500s every request, login included.

`.claspignore` is the guard, and `dev/verify.mjs` inverts the rule: **anything
in `portal/` that is not a known server file must be ignored
explicitly**. A new file or folder there therefore fails verification the day
it appears — fix it by listing it in `.claspignore`, or, if it really is server
code, by adding it to `SERVER_FILES` in `dev/verify.mjs`.

**Run `node dev/verify.mjs` from `portal/` before any `clasp push`.**

A push also deletes whatever the Apps Script project holds that this folder no
longer has. `App.html`, `Script.html` and `Styles.html` left with the PWA, but
`doGet` in `Core.js` still renders the `App` template for a request with no
action. After a push, that request throws. The agent only POSTs, so sign-in and
`aiindex` keep working. Before the first push, change `doGet` to answer JSON
for a request with no action.

### 4.3 The deployment id is the agent's lifeline

Aura Agent's `EXEC_URL` and `EXEC` in `dev/config.mjs` carry the `/exec` URL
and cannot discover a new one. Publishing through **"New deployment"** mints a
fresh id and retires the old one, and the agent loses its sign-in and its data.
**Always publish by editing the existing deployment.** If the id ever does
change, update `EXEC` in `dev/config.mjs` *and* `EXEC_URL` wherever the api
runs (invariant 8).

### 4.4 Secrets live in Script Properties and fail closed

`TOKEN_SECRET`, `PASSWORD_PEPPER` and `ADMIN_PASSCODE` are read from
*Project Settings → Script Properties*. They are never in the repo, and the code
throws rather than falling back to a default. Set them in any new Apps Script
project **before** deploying, or every login fails.

### 4.5 Cold reads are genuinely slow

`getHome_ → getFocus_ → getSearchIndex_` walks ~60 city tabs and measured
51–68s cold. Hence `CACHE_TTL = 21600` (the `CacheService` maximum), the
`warmCache()` time-trigger, and the chunked cache in `Core.js` (payloads over
45k chars are split across keys). This is also why Aura Agent caches `aiindex`
rather than calling it per question (invariant 4).

---

## 5. Commands

Run these from `portal/`:

```bash
node dev/verify.mjs                 # pre-push checks — must pass before clasp push
clasp status                        # list exactly what a push would upload
clasp push                          # publish the server files to Apps Script

node dev/serve.mjs                  # API-only stand-in on :4599 (fixture sign-in, proxies the rest)
```

`AK_EXEC=<url>` points the stand-in at a different deployment.
`bin/dev` starts the stand-in for you.

---

## 6. Architecture

Everything is one action on one endpoint: `app(action, params)` in `Core.js`.
`doPost` lands in `app()`.

Access control is the portal's own token layer, because the web app is
deliberately **anonymous** — realtors may have no Google account, and sign-in
has to be publicly reachable:

- `PUBLIC_ACTIONS` = `login`, `session`. They mint or refresh a token, and are
  POST-only so a password or token never lands in a query string or the
  execution log.
- Everything else goes through `requireAuth_`, which verifies the HMAC token and
  hands handlers the already-verified claims as `p.__tok`.
- Role checks (`p.__tok.role === 'admin'`) happen **on the server**.

Token shape: `base64url(user|role|credGen|issuedMillis) . base64url(HMAC-SHA256(raw, TOKEN_SECRET))`.
The timestamp is read **from the end**, so an older three-field token still
parses.

**Data.** Three spreadsheets, keyed in `SHEETS` (`main`, `deals`,
`onboarding`). City and school tabs put **headers on row 2, data from row 3**
(`HEADER_ROW`, `DATA_START`). Tab access is allow-listed; readers cache by tab
and header row.

---

## 7. Conventions

- Server files: ES5-flavoured house style, `var` and `function`, no arrow
  functions, no build step. `dev/*.mjs` is modern Node ESM (`const`, arrows,
  top-level `await`).
- A trailing underscore (`getHome_`, `requireAuth_`) marks a private helper.
- **Comments explain why, not what** — the reason a line exists, the failure it
  prevents, and what was measured.

**Do not:**

- put a secret, a sheet id you invented, or a hardcoded token in the repo
- add an npm dependency (`dev/` is dependency-free Node)
- widen `PUBLIC_ACTIONS` without a deliberate reason
- grow features here — new work belongs in the agent

---

## 8. Before you push

1. From `portal/`: `node dev/verify.mjs` — all checks pass.
2. `clasp status` — nothing unexpected in the upload list.
3. `clasp push`, then publish by **editing the existing deployment** — never
   "New deployment".
4. Substantive change → [`worklog.md`](worklog.md) has an entry for it.
