# Aura Agent — admin app

The desktop web app where an Aura Key admin runs and reviews what the agent
does: upload a project's builder PDFs, follow the Unbrander job, compare every
page before and after, download the result, edit the organization profile.

It is **not** the realtor PWA (the repo root) and shares no code with it. It talks
to one backend, `aura-agent/api/`, over its JSON API, with the same portal sign-in:
`POST /login`, then `GET /me` must say `admin` before the token is kept.

Hosting: Netlify, base directory `aura-agent/ui/admin/`, `VITE_AURA_BASE` set to the
Railway URL of the api (the `aura-chat` service). That URL is also in `netlify.toml`'s CSP
`connect-src`; when it moves, change both, and add the site's origin to
the api's `ALLOWED_ORIGINS`.

Before building or changing a screen, read [DESIGN.md](DESIGN.md): the colours,
type, surfaces and copy rules every screen follows.

## Commands

```bash
npm ci
cp .env.example .env.local   # VITE_AURA_BASE=http://localhost:8000
npm run dev                  # :5173 (in the api's ALLOWED_ORIGINS locally)
# or, from the repo root, the whole stack: aura-agent/bin/dev
npm run lint && npm run typecheck && npm test   # the gate; tests never touch the network
npm run api:types            # regenerate src/api/schema.d.ts after an API change
npm run build
```

## Where things go

```
src/
  app/            the shell: providers, routes.tsx (every route), layout/. Wiring only.
  api/            the ONLY code that calls fetch or XMLHttpRequest. One module per resource.
                  schema.d.ts is generated (npm run api:types) — never edit it.
  components/ui/  primitives (Button, Input, ...): look only, no app logic
  components/     shared composed components — every one listed in COMPONENTS.md
  features/<area>/ one folder per area of the app: its pages, its components/, its hooks/
  lib/            pure helpers (no React, no network)
  styles/         tokens.css (brand values) and globals.css (Tailwind theme)
  test/           MSW handlers (a fake Aura), setup, renderApp helper
```

## Rules (ESLint enforces the first three)

- **Only `src/api/` talks to the network.** Screens use it through TanStack Query
  hooks in their feature's `hooks/`, never by calling `api/` in an effect.
- **`components/` never imports `features/` or `app/`.** A feature never imports
  another feature: what two features need moves to `components/` or `lib/`.
- **Reuse before writing.** Read `COMPONENTS.md` first. One feature-local copy of a
  pattern is fine; when a second screen needs it, move it to `components/` and add
  its entry (a test fails without one).
- **Every failure has a place on the screen.** A query's error renders
  `ErrorState` with Retry; a mutation's error is shown where the action was or as a
  toast; a 422's `ApiError.fields` go onto the form's fields. Never a blank area,
  never only a console line.
- **No `dangerouslySetInnerHTML`, no third-party scripts.** File names, project
  names and instructions come from uploads: render them as text.
- **Times are shown in America/Toronto**, through `lib/format.ts`.
- **Types come from the API.** Use `components["schemas"][...]` from
  `api/schema.d.ts`; do not hand-write a type the backend already declares.
- Tests: Vitest + Testing Library + MSW. Query by role and label as a person
  would; an unmocked request fails the test.

Why it is built this way: the 2026-10-13 entries in `aura-agent/docs/worklog.md`.
