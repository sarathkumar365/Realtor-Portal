# Unbrander — design index

Requirements for adding builder-document unbranding to the Realtor Portal agentic system.
This folder is the hand-off: design only, built in the portal project.

## Summary

Staff upload builder PDFs in the portal UI. The agent proposes the project, builder, city and
document types, and staff confirm them. Each document is unbranded with the existing
`unbrand-builder-docs` skill in a sandbox, then checked by code and by a visual model check.
Clean files are filed privately in Drive under a configured folder tree. A human approves.
Approval makes the link public and registers it in the portal in one action.

The models never touch Drive, sharing or the portal. Only code does, and only after approval.

## Documents

| Phase | Document | State |
|---|---|---|
| 1. Whiteboard | [WHITEBOARD.md](WHITEBOARD.md) | Decided |
| 2. Loop and architecture | [LOOP.md](LOOP.md) | Proposed |
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

## Open questions to settle in the portal project

1. Where site plans and feature sheets go in Drive (default: project folder root).
2. One job = one project? (default: yes)
3. Model per call, and the cost ceiling per document (measure first).
4. Today's manual time per document (needed as a baseline).
5. How staff identify project and builder today (to confirm with the team).
6. Whether the portal has a job queue and secret store to reuse (assumed yes).
7. The system's exact name (this design calls it the Realtor Portal).

## Build order (suggested)

1. Spike: run the skill in the portal's sandbox on 3 real documents.
2. Golden dataset from the existing Unbranded Drive tree, plus the code checks.
3. Pipeline to `FILED_PRIVATE` in dry-run mode.
4. Approval screen and publish step.
5. Metadata extraction (M1) and pre-fill.
