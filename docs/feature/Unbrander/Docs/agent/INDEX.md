# Unbrander — design index

Requirements for adding builder-document unbranding to the Realtor Portal agentic system.
This folder is the hand-off: design only, built in the portal project.

## Summary

Staff upload builder PDFs in the portal UI. The agent proposes the project, builder, city and
document types, and staff confirm them. Each document is unbranded by Claude calling a fixed
set of PDF tools that run in Aura Chat (the logic of the existing `unbrand-builder-docs`
skill, moved into code), then checked by code and by a visual model check. Clean files are
filed privately in Drive under a configured folder tree. A human approves. Approval makes the
link public and registers it in the portal in one action.

The models never touch Drive, sharing or the portal. Only code does, and only after approval.

## Decisions taken (2026-10-05)

| # | Decision | Where |
|---|---|---|
| D1 | Unbrander is built inside Aura Chat, which becomes write-capable from this feature on | LOOP.md, `invariants.md` §5 |
| D2 | After approval the system files, shares and registers automatically (not staff by hand) | LOOP.md |
| D3 | M2 uses **named PDF tools** run by our code, not model-written code in a sandbox | LOOP.md, SECURITY.md |
| D4 | Publish fills the **existing `UNBRANDED` cell** of the project row (today's "Drive" button, `Core.js:85`). A filled cell means "existing project" | LOOP.md, AUTONOMY.md |
| D5 | Upload screen is admin-only, gated by user role | SECURITY.md |
| D6 | Job state and queue live in the existing Railway Postgres (`jobs` table) | LOOP.md |
| D7 | Drive and sheet writes are made **directly by Aura Chat** through the Google Drive and Sheets APIs (revised 2026-10-06; Apps Script route dropped). Credential type depends on where the Unbranded tree lives | LOOP.md, SECURITY.md, `invariants.md` §2 |
| D8 | PDF libraries: **PyMuPDF** (unmodified, AGPL-3.0) and **reportlab**. Later only if needed: pdfplumber, ocrmypdf | SECURITY.md |
| D9 | UI is a **separate admin app** (the start of the Aura Agent UI), not the PWA | LOOP.md |
| D10 | Agent loop stays on PydanticAI while Unbrander is built; **migration to LangChain / LangGraph is phase U8**, after go-live (2026-10-06) | PHASES.md |
| D11 | Five-port cap lifted; new ports still need a stated reason | `AGENTS.md` |
| D12 | Files between steps live on a **Railway volume** | SECURITY.md |
| D13 | Project not in the sheet: the admin app asks the admin what to do | AUTONOMY.md |
| D14 | Admin app: **Vite + React + TypeScript**, its own Railway service | LOOP.md |
| D15 | New ports `JobStore` (Postgres) and `GoogleWriter` (Drive + Sheets); the PDF tools are plain code, not a port. Worker runs inside the Aura Chat service | LOOP.md |
| D16 | M2/M3 model chosen by the golden set: cheapest vision + tool-calling model with zero leaks, via OpenRouter | EVALUATION.md |
| D17 | Google credential: a **service account**; the Unbranded tree moves into a **Shared Drive** with the service account as a member, and the sheet is shared with it as Editor | SECURITY.md |

## Documents

| Phase | Document | State |
|---|---|---|
| 1. Whiteboard | [WHITEBOARD.md](WHITEBOARD.md) | Decided |
| Build phases | [PHASES.md](PHASES.md) | Cut 2026-10-06 |
| 2. Loop and architecture | [LOOP.md](LOOP.md) | Decided (D1–D17); details proposed |
| 3–4. Autonomy and decision rule | [AUTONOMY.md](AUTONOMY.md) | Proposed |
| 5. Context | [CONTEXT.md](CONTEXT.md) | Proposed |
| 6–7. Failure modes, metrics, evals | [EVALUATION.md](EVALUATION.md) | Proposed |
| 8–9. Security and operations | [SECURITY.md](SECURITY.md) | Proposed |

"Proposed" means the operator accepted the defaults without reviewing each one. Review them
before the build.

## Deferred by decision

- WhatsApp listener as an intake adapter (needs a spike: official channel, ban risk, groups).
- Overwrite or backup when a project is updated. Until decided, a human handles updates.
- Broker portal downloads (manual).
- Auto-publish (only after the criteria in AUTONOMY.md are met).

## Open questions

1. Where site plans and feature sheets go in Drive (default: project folder root).
2. One job = one project? (default: yes)
3. Model per call, and the cost ceiling per document (measure first).
4. Today's manual time per document (needed as a baseline).
5. How staff identify project and builder today (to confirm with the team).
6. Which app Sudhanshu's team runs the skill in today (chat, Cowork). Does not change the
   design; useful for comparing outputs.
8. How the golden set is graded (LLM judge or other) — to discuss.

## Build phases

See [PHASES.md](PHASES.md): U0 prerequisites, U1 spike, U2 PDF tools and evals, U3 pipeline
to `FILED_PRIVATE`, U4 admin app, U5 approve and publish, U6 metadata extraction, U7
hardening, U8 agent loop migration to LangChain / LangGraph.
