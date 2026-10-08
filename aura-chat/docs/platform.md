# Aura Agent — the platform

What Aura Agent is for, what a capability is, and the rules every capability follows.
Referenced from [`../AGENTS.md`](../../AGENTS.md).

## Purpose

Realtors and staff at Aura Key Realty spend their day on manual tasks: answering the
same project questions, cleaning builder documents, filing them in Drive, copying links
into the sheet. Aura Agent exists to **automate those tasks**, one at a time, until it runs
most of them itself and people only make the decisions that need a person.

It started as Aura Chat, a read-only assistant. From October 2026 it is a realtor agent
with several capabilities. The code stays in `aura-chat/` until the folder rename, which is
deferred until the current feature work is done.

## What a capability is

One task the agent takes over, end to end. Today:

| Capability | Task it takes over | State |
|---|---|---|
| Chat | Answering project questions from the brokerage's records | Live |
| Unbrander | Unbranding builder PDFs, filing them, linking them in the sheet | Building |

More are added after Unbrander. Each one is a self-contained slice of the same service:
it shares auth, Postgres, the portal client and the admin app, and owns its tools, its
pipeline and its tests.

## Who the agent works for

One deployment serves one organization (decided 2026-10-08). A second brokerage gets its
own service and database, not a row in this one: serving several from one deployment
would put an organization id on every table and query, and into the portal token and
Client Mode, for a need nobody has yet.

Who that organization is — its name, the assistant's name, its region and its brand mark
— is one platform object, `Organization` in `app/domain/organization.py`, built in
`container.py` and handed to every capability. No capability writes the brokerage's name,
colours or font itself. Admins edit the profile from the admin app; until it is saved,
defaults in code apply. Built in Unbrander phases U2b to U4
([PHASES.md](feature/Unbrander/PHASES.md)).

Three kinds of setting, kept apart:

| Kind | Examples | Changed by | Lives in |
|---|---|---|---|
| Organization profile | name, region, brand mark | an admin, rarely | `organization` table, edited in the admin app |
| Engineering settings | models, rounds, limits | a developer | `app/config.py` and the environment |
| Per-job input | builder and project names | an admin, every job | the job record |

## How a capability is added

1. **Design first**, in `aura-chat/docs/feature/<Name>/`, with the agent-design phases: whiteboard,
   loop, autonomy, context, evals, security, then build phases. Decisions are recorded with
   the alternatives rejected.
2. **Cut phases** that each end in something demoable, starting with a spike of the
   riskiest dependency.
3. **Build in this repo**, as a slice in `aura-chat/app/capabilities/<name>/` with its
   own `domain/`, `ports/` and `adapters/`, wired in `container.py`. It may use the
   shared platform in `app/` but never another capability. A new port needs a stated
   reason and agreement.
4. **Record why** in [`worklog.md`](worklog.md), and add the capability to the tables in
   this file, in `AGENTS.md` and in the roadmap.

## Rules every capability follows

- **Code orchestrates; models judge.** The order of steps is code. A model is called only
  where judgement on unstructured input is needed, and it calls named tools — never
  arbitrary code.
- **Writes need a human until autonomy is earned.** Anything public or hard to undo waits
  for an admin's approval. Auto-approval is earned per action type with measured results,
  never assumed.
- **Untrusted content never reaches a model that can act.** Text from documents, sheets or
  messages is data. A model that reads it has no tool that writes outside its own sandbox
  of one document.
- **Least privilege.** Reads use the caller's own token. A write credential is scoped to
  exactly what the capability touches and is never in a model's context.
- **Every action is logged with its reason**, and every write can be undone.
- **A golden set gates changes.** Each capability has an eval set from real, expert-labelled
  examples; a change to a prompt, a model or a tool runs it.
- **Momentum over preparation.** Build the current capability end to end; do only the
  platform work it needs. Heavy migrations wait until it ships.

The full security rules are the invariants: [`aura-chat/invariants.md`](feature/aura-chat/invariants.md).
