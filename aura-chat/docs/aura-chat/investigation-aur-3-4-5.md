# AUR-3 / AUR-4 / AUR-5 — Discovery findings

**Date:** 2026-08-24 · **Investigator:** Sarath · **Scope:** the three Day 1 discovery
tickets that everything else in the Aura Chat sprint is built on.

| Ticket | Question | Verdict |
|---|---|---|
| AUR-3 | What is the live project data source, and what is its schema? | **Answered — with a blocking gap** |
| AUR-4 | What login/auth does Aura Chat reuse? | **Answered — reusable as-is** |
| AUR-5 | What is the project-page URL / deep-link pattern? | **Answered — the pattern does not exist** |

AUR-2 (server hardware) is out of scope: we are going through **OpenRouter**, so there is
no local model server to size. See *Consequences for the rest of the board* below for what
that changes.

---

## 1. What the system actually is

Two front ends, one back end, three spreadsheets.

```
www/  (PWA on Netlify)  ─┐
                         ├─► POST {action, auth, …}  ─►  Apps Script web app  ─►  Google Sheets ×3
App.html + Script.html  ─┘        (one JSON endpoint)         Core/Sheets/Team/External.js
   (Apps Script HtmlService)
```

- The back end is a single Apps Script project (`scriptId` `1vyucrQWS0…uL8F`), deployed as a
  web app with **Execute as: the deploying account**, **Access: anyone, anonymous**
  ([appsscript.json](appsscript.json)). Anonymous is deliberate — realtors have no Google
  accounts — and access control is the token layer described in §3.
- Every request funnels through **one dispatcher**, `app(action, p)` in
  [Core.js:340](Core.js:340). `doGet`, `doPost` and the HtmlService bridge all call it, so
  there is exactly one place to add an action and one gate to pass.
- The PWA in `www/` is **generated** from `App.html` + `Styles.html` + `Script.html` by
  [dev/build.mjs](dev/build.mjs). `www/app.js` is not hand-edited — it is a copy of
  `Script.html`'s script body. The single behavioural difference is `window.AK_EXEC`, which
  flips `call()` from the `google.script.run` bridge to `fetch`.
- Live endpoint (from [dev/config.mjs](dev/config.mjs)):
  `https://script.google.com/macros/s/AKfycbxB20Mc56_q…DojC-g/exec`

**Implication for Aura Chat:** the AI backend should be a **new peer of this dispatcher**,
not a fork of it. It reads the same sheets, reuses the same token verifier, and adds its own
actions. Nothing above needs to be rewritten.

---

## 2. AUR-3 — The live project data source

### 2.1 Where the data lives

Three spreadsheets, declared in [Core.js:22](Core.js:22):

| Key | Spreadsheet ID | Holds |
|---|---|---|
| `main` | `1DSaHocXEpfCBoJgE8JUxKsoqrR-H8D08kTLP3hI9-l0` | ~60 city project tabs, BUILDERS, Contractors, Resources, FAQs, School Rankings, Events, Contacts |
| `deals` | `1FHi7550lIG4oQOWCt9HdLwLM84PxD_sgdEqeoiPsEWI` | Active Listings, Websites, DEALS |
| `onboarding` | `1DtIWnqR6LKN5AqlqwCNfoSk1FFsjEaPu` | Bootcamp weeks and progress |

A fourth spreadsheet — the **LOGIN sheet** — is addressed by the `LOGIN_SHEET_ID` Script
Property and is deliberately *not* in this map, so realtor credentials are not visible to
everyone the main sheet is shared with ([Sheets.js:301](Sheets.js:301)).

Tab access is allow-listed in `ALLOW` ([Core.js:76](Core.js:76)). A tab not on that list
cannot be read through the API at all.

### 2.2 How a project row is read

A "city tab" is any tab whose **row 2** has `PROJECT` in column A and `BUILDER` in column B
— that is literally the test `getCities_()` uses ([Sheets.js:262](Sheets.js:262)). Headers
are on **row 2**, data starts on **row 3** (`HEADER_ROW = 2, DATA_START = 3`).

Columns are matched by **fuzzy keyword against the header text**, not by position
(`FIELD_KEYS`, [Core.js:70](Core.js:70)). A tab can reorder or rename columns loosely and
still parse.

The record `getProjects_()` returns ([Sheets.js:70](Sheets.js:70)):

| Field | Source header keyword | Notes |
|---|---|---|
| `_row` | — | sheet row number |
| `project` | `PROJECT` | |
| `builder` | `BUILDER` | |
| `type` | `TYPE` | free text |
| `cats` | derived from `type` | `townhome` / `detached` / `semi` / `condo` |
| `occupancy` | `OCCUPANCY`, `OCCUPAN` | free text |
| `login` | `LOGIN` | builder-portal login |
| `office` | `OFFICE` | |
| `contact` | `CONTACT` | |
| `fub` | `FUB` | |
| `status` | `STATUS` | drives Focus and hidden |
| `live` | `LIVE ON`, `ON WEBSITE` | |
| `hidden` | derived from `status` | `/not\s*avail|unavailable/i` |
| `broker_url` | `BROKER` | real hyperlink, run link, `=HYPERLINK()` or bare URL |
| `drive_url` | `UNBRANDED` | |
| `website_url` | `LIVE LINK`, `LINK` | |

### 2.3 The blocking gap

**The city tabs carry no commercial data.** Not one of these fields exists anywhere in the
project reader:

> price · starting price · maximum price · deposit percentage · deposit schedule ·
> bedrooms · incentives · development charges · assignment · parking · maintenance fee ·
> ownership type (freehold/condo) · community · address · last-updated date ·
> source document · source effective date · ClientVisible · InternalNotes

The spec's flagship demo query — *"show detached under $1M"* (AUR-96, the Day 1 gate) —
**cannot be answered from the current schema.** `detached` resolves (via `cats`); `under
$1M` has nothing to compare against.

This is not a data-quality problem that AUR-69–74 will clean up. It is a **missing column
set**. Sudhanshu's data tickets assume the columns exist and need filling; in fact the
columns have to be created first.

### 2.4 Where price data might already exist

`ALLOW.main` lists tabs that **no screen in the app ever reads**:

`HotPriceSheet` · `HotDeals` · `PRECON` · `Precon Reserch - Prakash` · `RESALE` ·
`COMMERCIAL` · `Deposit Calculator` · `FocusProjects` · `Focus Dxb Projects`

They are reachable only through the generic `tab` action, which the UI never calls
(verified: no `call('tab'…)` in `www/app.js` or `Script.html`). `HotPriceSheet` and
`Deposit Calculator` are the obvious candidates for the pricing and deposit data the spec
needs.

> **Action — highest priority on the board.** Open `HotPriceSheet`, `Deposit Calculator`,
> `PRECON` and `HotDeals` and confirm whether they carry per-project pricing, and whether
> they can be joined to a city-tab row by project name. The answer determines whether
> AUR-25 is "map existing columns" or "design and populate a new schema", and that is a
> different-sized Day 1.

### 2.5 The search index — built, cached, and not exposed

`buildSearchIndex_()` ([Team.js:308](Team.js:308)) already walks all ~60 city tabs and
produces a flat cross-city array of `{city, project, builder, type, cats, broker_url,
drive_url, website_url, hasFub, _row, focus, occupancy}`. It is cached under `index_api`.

**It has no action in the dispatcher.** It exists only to feed `getFocus_()` and
`getCityCounts_()`. Nothing in the UI can search projects across cities — the Cities screen
searches *city names* only.

This is the single best piece of news in the investigation: `searchProjects` (AUR-25) is
mostly *exposing and filtering an index that already exists and is already warm*, not
building one.

### 2.6 Caching and freshness — what Aura Chat inherits

- `CACHE_TTL = 21600` (6 h, the CacheService maximum), with `warmCache()` on a 4-hourly
  trigger, so a cold rebuild is rare ([Core.js:120](Core.js:120)).
- Values over 100 KB are transparently split across `k|0…k|n-1` chunks
  (`cachePutStr_`/`cacheGetStr_`) — the index is 300 KB+ and would otherwise never cache.
- `?fresh=1` forces a rebuild, rate-limited to **one per action per 30 s**
  (`freshAllowed_`).
- `cachedBuild_` holds a script lock so five realtors arriving on a cold cache do not start
  five 60-second rebuilds.

**Consequence for AUR-32 (source metadata):** "last updated" today means *when the cache
entry was built*, not when a human last edited the row. Every reader stamps
`updated: new Date().toISOString()` at build time. Aura Chat must not present that as data
freshness — a `LastUpdatedAt` column has to come from the sheet.

**Consequence for AUR-65 (<10 s):** a warm index read is fast; a cold rebuild is ~60 s. The
budget holds only if Aura Chat reads the *cached* index and never triggers a rebuild on a
user's request.

---

## 3. AUR-4 — The authentication Aura Chat reuses

### 3.1 The mechanism

A **signed, self-contained bearer token** — not a Google session, not a cookie.

```
raw   = username | role | credGen | issuedAtMillis
token = base64url(raw) + "." + base64url(HMAC-SHA256(raw, TOKEN_SECRET))
```

`makeToken_` / `checkToken_` at [Sheets.js:465](Sheets.js:465). Verified live: a GET without
a token returns `{"ok":false,"error":"login required"}`; a GET carrying `auth` is refused
with `use POST when sending auth`.

Sign-in (`handleLogin_`, [Sheets.js:410](Sheets.js:410)):

1. Global lockout check — 60 failures across all accounts in 15 min closes sign-in.
2. Per-user backoff `[0, 1, 2, 4, 8] s`, charged **before** the comparison so timing leaks
   nothing.
3. Admin path: `ADMIN_ID = 'admin'` + `ADMIN_PASSCODE` Script Property → `role: 'admin'`.
4. Realtor path: the LOGIN tab, matched case-insensitively on username →
   `role: 'realtor'`.
5. Passwords are `sha256$` + base64url(SHA-256(`PASSWORD_PEPPER|username|password`)).
   Legacy plaintext rows migrate to a hash on first successful sign-in.

### 3.2 The four properties that matter to Aura Chat

| Property | Behaviour | Why Aura Chat cares |
|---|---|---|
| **Stateless** | Everything needed to verify is in the token + Script Properties. No session store. | The AI backend can verify a token **without a round trip to the portal**. |
| **Sliding 7 days** | `SESSION_MS = 7d`; every launch calls `session` and mints a fresh token. | A long chat session will not expire mid-conversation. |
| **Revocable** | `credGen_` fingerprints the stored password hash and is baked into the token. Change a password → every token it minted stops verifying. | Real per-user revocation, which Aura Chat inherits free. |
| **Liveness-checked** | `userStillActive_` re-reads the LOGIN tab (5-min cache). Delete a row → access dies within 5 min. | A removed realtor loses Aura Chat too. |

### 3.3 Identity available to the AI backend

`checkToken_` returns `{user, role, issued}`.

- `user` — the LOGIN username. **This is the `user_id` for `ai_conversations` /
  `ai_messages` (AUR-36/37).** It is a human-typed string that can itself contain `|`,
  which is why the token is parsed from the *end*, not the front (see commit `61b06fc`).
  Treat it as an opaque string; do not re-split it.
- `role` — `'admin'` or `'realtor'`. **There is no third role, and nothing today
  distinguishes Realtor Mode from Client Mode.** Client Mode (AUR-55–58) is a *request
  parameter Aura Chat introduces*, not something the token carries. That is fine — but it
  means the mode must be validated and applied server-side on every call, and stored with
  the conversation (AUR-57), because a client-supplied flag is the only signal.
- The display name is **not** in the token; the client keeps it from sign-in. If Aura Chat
  wants "Hi Sarath", it reads it from `login`'s response or from the LOGIN tab.

### 3.4 Rules the AI endpoint must not break

1. **POST only for anything carrying `auth`.** Enforced in `doGet`
   ([Core.js:307](Core.js:307)) because a token in a query string lands in the execution
   log, browser history, and the `Referer` of any outbound link.
2. **`Content-Type: text/plain;charset=utf-8`**, body = JSON. This makes it a CORS *simple
   request* — no preflight, which Apps Script cannot answer ([www/app.js:56](www/app.js:56)).
3. **Gate before dispatch.** `app()` checks `hasOwnProperty` against `PUBLIC_ACTIONS` — a
   bare lookup would let `constructor` and `toString` walk straight past the gate.
4. **Reuse the verified token.** `app()` puts it on `p.__tok`; handlers must not re-verify.
5. **Fail closed.** `TOKEN_SECRET` and `PASSWORD_PEPPER` have *no in-source fallback* —
   missing means throw. Confirm with `checkSecret()` before any deploy.

### 3.5 Verdict

**AUR-4 needs no new work.** Aura Chat's endpoint calls `checkToken_(p.auth)` +
`userStillActive_(t.user)` and it is authenticated — two function calls, both already
written. Since the AI backend lives inside Apps Script (§5), `app()`'s existing gate does
this before the handler is even reached; the handler just reads `p.__tok`.

---

## 4. AUR-5 — Project page URLs and deep links

### 4.1 Finding: there is no project page

Routing is hash-based, `#<view>[/<arg>]` (`go()` / `routeInner()`,
[www/app.js:217](www/app.js:217)). Registered views are in `LOAD`
([www/app.js:213](www/app.js:213)).

The deepest route that exists is:

```
#city/<CITY%20NAME>      e.g.  #city/BRAMPTON
```

`loadCityDetail(name)` ([www/app.js:494](www/app.js:494)) renders every project in that city
as a **card in a list**. There is no `#project/…` route, no project detail screen, and no
per-project anchor. A project card offers exactly three things: `linkBtn('Builder',
broker_url)`, `linkBtn('Drive', drive_url)`, `linkBtn('Website', website_url)` — all of
which are **external** links to builder portals, Google Drive folders and public project
websites.

### 4.2 Finding: there is no project ID

Nothing in the system assigns a project a stable identifier. A project is addressed only by
the tuple **(city tab, `_row`, project name)**. `_row` is a live sheet row number — insert
a row above and it changes.

This directly blocks:

- **AUR-26 `getProject(projectId)`** — there is no `projectId` to accept.
- **AUR-27 `compareProjects(projectIds[])`** — same.
- **AUR-47 "View Project deep link on every card"** — there is no destination.
- **AUR-79 "100% correct project deep links"** — nothing to verify.
- **AUR-54 "Ask Aura About This Project"** — there is no project page to put the button on.
- **AUR-70** lists `ProjectID` as a required column. It does not exist.

### 4.3 What this costs

The Day 1 gate (AUR-96) is stated as: *login → "show detached under $1M" → real Aura
projects → tap a project → the existing project page opens.*

**"The existing project page" does not exist.** The gate as written cannot pass on Day 1
without building one. This is the single largest undiscovered item in the sprint, and it
sits on the critical path of the Day 1 gate.

### 4.4 Options

| Option | Work | Consequence |
|---|---|---|
| **A — Build a real project page.** Add `ProjectID` to the city tabs, a `getProject` action, and a `#project/<id>` route in `LOAD`. | ~half a day, plus Sudhanshu populating IDs across the priority projects | Satisfies AUR-5/26/27/47/54/79 properly. Deep link is `#project/<id>`, stable across sheet edits. |
| **B — Deep-link to the city, scroll to the project.** `#city/BRAMPTON?p=<slug>`, anchored on a name slug. | ~2 hours, no schema change | No new page, no ID column. But the "link" is a scroll position, not a record, and it breaks when a project is renamed. Fails the spirit of AUR-79. |
| **C — Link out to `website_url`.** Reuse what the cards already do. | zero | Sends the realtor to a *builder's* site, not to Aura's record. Not a portal deep link; AUR-47 is not met in any meaningful sense. |

**Recommendation: A.** B and C both leave AUR-26/27 without a `projectId`, which means the
spec's compare feature has nothing to key on. Adding `ProjectID` is required by AUR-70
regardless, so the marginal cost of A over B is the route and the page — and the page is
mostly the card that already exists, on its own screen.

> **Decide this with Sudhanshu on Monday morning**, because A needs a column populated
> before anything downstream works, and that is his queue, not yours.

---

## 5. Where the AI backend should live

**Decision: inside Apps Script.** Aura Chat becomes new actions in the existing
dispatcher, calling OpenRouter through `UrlFetchApp`.

The reuse question splits into three layers, and only the third was ever genuinely open:

| Layer | What it is | Verdict |
|---|---|---|
| **1 — Data + auth** | `getProjects_`, the cached cross-city index, `checkToken_` | Reuse entirely. Never in question. |
| **2 — AI tools** | `searchProjects`, `getProject`, `compareProjects`, `getRecentProjects` | New `case` entries in `app()`, beside `getProjects_`, reading the same cache. Reuse. |
| **3 — Model loop** | Prompt assembly, function-calling round trips, conversation storage | The only open question. **Apps Script.** |

Note that even a separate service would not re-read the Sheets — it would call this API as
an authenticated client. "Outside" never meant rebuilding the fetching.

**Why inside wins for a 2-day MVP:** one deploy target, one auth path, no duplication of
`TOKEN_SECRET`, and `UrlFetchApp` talks to OpenRouter without ceremony. `ai_conversations`
and `ai_messages` as Sheet tabs are unglamorous but adequate at team scale — append under a
`LockService` lock, read and filter by `conversation_id`.

**On streaming (AUR-44):** its acceptance criterion is *"The Realtor sees that Aura is
working, not a frozen screen."* A spinner satisfies that as written. Apps Script cannot
stream tokens (`UrlFetchApp` blocks and returns a complete response; `ContentService`
cannot serve SSE), but the ticket does not require token-by-token output. Do not let this
drive the architecture.

### 5.1 The one real risk: a shared runtime budget

Apps Script's daily script runtime is a **single budget shared with the portal itself**, and
a chat turn is expensive. Model → tool call → model is 2–4 sequential round trips, and the
script is blocked and accruing runtime for the whole time it waits on OpenRouter — call it
5–15 seconds of runtime per question.

The comment at [Core.js:120](Core.js:120) — *"~90 of those exhaust a consumer account's
whole daily runtime"* — indicates the ceiling was understood to be 90 minutes/day. If that
is still the tier, Aura Chat gets roughly 400–800 questions/day across the team, minus what
the portal already spends on index rebuilds and `warmCache`.

The danger is not the number; it is the **shared failure domain**. Exhaust the quota with
chat and Home stops loading too.

> **Action before AUR-13:** confirm the deploying account's tier in the Apps Script
> dashboard. Consumer Gmail is 90 min/day; Google Workspace is 6 hours. At 6 hours this
> concern largely evaporates.

**Mitigation either way, and it is cheap:** rate-limit chat on its own counter, separate
from the portal's. AUR-21 already exists for this — scope it so chat can starve without
taking Home down with it.

The 6-minute per-execution cap is not a concern: a single chat turn will not approach it.

### 5.2 When to revisit

Move layer 3 out only if one of these actually bites after launch: the daily runtime budget
is exhausted in normal use; token streaming becomes a stated requirement rather than a
nice-to-have; or `ai_messages` outgrows a Sheet tab. None of them are Day 1 or Day 2
problems.

## 6. Consequences for the rest of the board

### Now unblocked or cheaper

- **AUR-4 → effectively done.** The auth mechanism is documented and reusable as-is. Close
  it once the shape decision in §5 is made (that decides *how* it is reused).
- **AUR-25 `searchProjects`** is cheaper than scoped — `buildSearchIndex_` already produces
  the cross-city array; the work is exposing it as an action and adding filters.
- **AUR-9/10 (provider-agnostic config)** is nearly free with OpenRouter: swapping models is
  a `model` string, and it is the same API surface. AUR-10's "prove the swap" is a config
  change and one request.
- **AUR-7/8/11/12 (Ollama install, serve, health, keep private)** are **obsolete** as
  written. OpenRouter means no local runtime. AUR-11 still matters as a *latency baseline*
  and AUR-12 becomes "keep the OpenRouter API key server-side, never in the client."

### Newly blocked or larger than scoped

- **AUR-5 is not a discovery ticket — it is a build ticket.** There is no project page. See
  §4.4.
- **AUR-96 (Day 1 gate) cannot pass as written** until AUR-5 option A ships.
- **AUR-25/26/27/31/34 all depend on commercial columns that do not exist.** §2.3.
- **AUR-70 is bigger than "fill in the fields."** Roughly two-thirds of the required
  columns have to be *created* on ~60 tabs, not populated. Depth-over-breadth (AUR-69, the
  30–50 priority projects) is now not just advice — it is the only way this fits in a day.
- **AUR-32 (source metadata)** needs a real `LastUpdatedAt` in the sheet. The `updated`
  field every reader returns is a cache-build timestamp and would be misleading.
- **New ticket needed: audit the unread tabs** (`HotPriceSheet`, `Deposit Calculator`,
  `PRECON`, `HotDeals`) for existing pricing data. This gates the size of AUR-25 and
  AUR-70 and should run before Monday's kickoff if at all possible.

### Two cross-owner dependencies to raise at kickoff

1. **`ProjectID` (Sudhanshu) blocks AUR-26, 27, 47, 54, 79 (Sarath).** Nothing keyed on a
   project ID can be built until the column exists and is populated.
2. **`IsCurrent` labelling (AUR-72, Sudhanshu) blocks AUR-30 (Sarath)** — already on the
   board, and still the correctness gate on the price-list rule.

---

## 7. Verification notes

What was checked, and how, so this can be re-run:

- **Live endpoint reachable and fail-closed.** `GET …/exec?action=cities` →
  `{"ok":false,"error":"login required"}`; `GET …&auth=x` → `use POST when sending auth`.
  No credentials were used.
- **`www/app.js` is generated, not authored.** `loadCityDetail` and the `LOAD` table appear
  identically in `Script.html` at the same relative positions; `dev/build.mjs` documents the
  derivation.
- **No project route.** `LOAD` enumerates every routable view; there is no `project` key,
  and `grep` for `#project` returns nothing.
- **Search index unexposed.** `getSearchIndex_` has no `case` in `app()`'s switch; its only
  callers are `getFocus_` and `getCityCounts_`.
- **Generic `tab` action unused by the UI.** No `call('tab'…)` in either front end.
- **Not verified — needs sheet access:** the actual contents of `HotPriceSheet`,
  `Deposit Calculator`, `PRECON`, `HotDeals`; whether any city tab carries a price column
  under a header keyword `FIELD_KEYS` does not look for; and whether the Script Properties
  (`TOKEN_SECRET`, `PASSWORD_PEPPER`, `ADMIN_PASSCODE`, `LOGIN_SHEET_ID`) are set — run
  `checkSecret()` in the editor to confirm.
