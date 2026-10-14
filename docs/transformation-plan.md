# Plan: the repo becomes Aura Agent only

Status: proposed, 2026-10-14. Nothing below is done yet.

## Decisions

- The PWA is retired. Nobody uses it. Its front end, build, hosting and assets leave the repo.
- **Later:** the Apps Script back end gets replaced inside the agent, with the agent's own users and login, and the Sheet read with the service account. Chat is not in active use, so this waits.
- **Later:** the Chat UI gets built in the admin app.
- **Until then:** the deployed Apps Script keeps running unchanged. The admin app still signs in through its `login` action. `aiindex` still backs the Chat API.
- **No `clasp push` in this plan.** The live Apps Script is not touched. That removes the main risk: a bad push 500s every login.
- Railway: only `dev` for now. `production` gets deleted.

## What stays, what goes

| Path | Fate | Why |
|---|---|---|
| `App.html`, `Script.html`, `Styles.html` | Delete | The PWA's UI. Includes the old Chat and Reports screens |
| `www/` (untracked), root `netlify.toml`, `.netlify/` | Delete | The PWA bundle and its Netlify site config |
| `dev/build.mjs`, `dev/deploy.mjs`, `dev/config.mjs` | Delete | They build and deploy the PWA |
| `assets/`, `design_handoff_aura_key/` | Delete | PWA icons, gate image, login design |
| `Core.js`, `Sheets.js`, `Ai.js`, `Team.js`, `External.js`, `Tax.js`, `Audit.js`, `appsscript.json`, `.clasp.json`, `.claspignore` | Keep for now, moved to `aura-agent/portal/` | The source of the back end that still runs. It is needed to fix login or `aiindex` until the replacement lands. Deleted with the replacement |
| `dev/serve.mjs`, `dev/authshim.mjs` | Keep, moved to `aura-agent/portal/dev/`, trimmed to `/api` only | `bin/dev` uses them as the local portal stand-in |
| `dev/verify.mjs` | Trim to the server checks | Its PWA checks (App.html, #chat, the bundle) go. Its `.claspignore` and global-scope checks still guard a future push |
| `aura-chat/` (untracked, holds a `.env`) | Delete after you confirm nothing in it is needed | A leftover from the move |
| Chat capability in `api/` | Keep, parked | The API, store and tests stay green. It has no UI until the admin app gets a Chat page |

When this is done, the repo root holds only `aura-agent/`, `AGENTS.md`, `CLAUDE.md` and `.gitignore`.

## Phases

Each phase is one commit. Each one gets a review and your go-ahead before commit and push.

### Phase 0: safety (now)
- Add `.env` and `.env.*` (except `.env.example`) to the root `.gitignore`. Today `aura-chat/.env` is not ignored, and a `git add .` would commit it.
- You delete the `production` environment in the Railway dashboard. The CLI isn't logged in to the new account, and the Railway tools here can't delete an environment.
- Done when `git check-ignore aura-chat/.env` matches and Railway lists only `dev`.

### Phase 1: point everything at the new api
- `aura-agent/ui/admin/netlify.toml:37` CSP `connect-src` becomes `https://api-dev-cf94.up.railway.app`.
- `aura-agent/api/scripts/deploy.sh:10` default `BASE` becomes the same.
- `dev/config.mjs` is skipped because Phase 2 deletes it.
- Railway dev `ALLOWED_ORIGINS` becomes the admin app's Netlify origin only. `aurakey.netlify.app` (the PWA) is dropped. **Needed from you:** the admin app's Netlify URL.
- Netlify admin site: base directory becomes `aura-agent/ui/admin` (dashboard).
- Done when the deployed admin app signs in against `api-dev-cf94` and `/doctor` is green with a real token.

### Phase 2: remove the PWA
- Delete the files in the "Delete" rows above.
- Move the kept Apps Script files into `aura-agent/portal/`, including `.clasp.json` with `rootDir` and `.claspignore` adjusted. Nothing is pushed.
- Trim `dev/serve.mjs` (drop the App.html serving and the `google.script.run` shim) and `dev/verify.mjs` (drop the PWA checks).
- `aura-agent/bin/dev`: run the stand-in from its new path, and drop `localhost:4600` from `ALLOWED_ORIGINS`.
- `api/app/config.py:15` default `allowed_origins` becomes `http://localhost:5173`.
- `tests/test_cors.py`: replace the PWA origins with the admin app's. Same assertions.
- Done when `pytest -q`, the admin app's lint, typecheck and tests, `node aura-agent/portal/dev/verify.mjs` and `aura-agent/bin/dev` all pass.

### Phase 3: docs
- `AGENTS.md`: drop "reuses the PWA"; §6 becomes "the portal back end (to be replaced)"; the layout gains `portal/`.
- `aura-agent/docs/portal.md`: rewrite as the back end only: what the agent calls (`login`, `session`, `aiindex`), and that no push is planned.
- Remove PWA mentions from `operations.md`, `architecture.md`, `how-it-works.md`, `api.md`, `the-agent.md`, `roadmap.md`, `working-rules.md`, `api/README.md`, `DEPLOY.md` (also: project `aura-agent`, env `dev`), the Unbrander docs and `ui/admin/AGENTS.md`.
- `roadmap.md`: add two items: the portal replacement (own users and login, Sheet via service account) and the Chat page in the admin app.
- `known-issues.md`: add an entry that Chat answers carry deep links into PWA screens that no longer exist (`agent_pydantic.py:79`, prompts). It is parked with Chat.
- `worklog.md`: one entry saying why the PWA was removed and why the back end stays until it is replaced.

### Phase 4: shut down the old hosting (dashboard, by you)
- Old Railway account: stop or delete `aura-chat-production-0711`. Nothing calls it once the PWA is gone.
- Netlify: delete the PWA site `aurakey.netlify.app`.
- Optional: rename the GitHub repo `Realtor-Portal` to `aura-agent`. Railway and Netlify follow a rename, but check both after.

## Later (not in this plan)
- Replace the portal back end inside the agent. That is an auth change and a schema change, and it breaks invariants 1, 2 and 8 as written, so it gets its own design doc.
- The Chat page and Reports in the admin app. The admin app opens up to realtors.
- After both: delete `aura-agent/portal/` and the Apps Script deployment.

## Risks
- The admin app sign-in depends on the live Apps Script. Phase 2 deletes only source. The deployment keeps answering. Check: sign in on the admin app after Phase 2 ships.
- A later `clasp push` from `aura-agent/portal/` with a wrong `rootDir` uploads nothing, or the wrong files. Check: `verify.mjs` runs before any push. `.clasp.json` paths are verified in Phase 2.
- `doGet` with no action still renders `App`, which is gone from the source. That only matters on a future push. The replacement removes it anyway.
