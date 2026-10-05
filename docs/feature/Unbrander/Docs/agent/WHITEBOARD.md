# Phase 1 — Whiteboard

Patterns applied: 1 (whiteboard capabilities), 2 (evolve architecture).

## Current manual process

Source: walkthrough with Sudhanshu Ranjan.

| # | Step | Today | Task type | Needs a model |
|---|---|---|---|---|
| 1 | Intake | Builders post documents in WhatsApp groups. Some are downloaded from builder broker portals (public or login). | fetch | No, unless the message must be parsed for project and builder |
| 2 | Unbrand | Staff open a new Claude chat, attach files, run `aura-key-admin:unbrand-builder-docs` with project and builder name. | judge | Yes (existing skill) |
| 3 | File | Google Drive: Unbranded → Ontario → City → project folder (project + builder). Price list at the project root; multiple floor plans in a `Floor Plans` subfolder. | act | Only to classify document type and pick the city |
| 4 | Share | Set the project folder link to "anyone with the link can view". Copy the link. | act | No |
| 5 | Publish | Add the link with the project heading in the Realtor Portal. The portal picks it up. | act | No |

## Known facts

- Volume: 5 to 10 documents per day.
- Realtor Portal: a web app backed by a Google Sheet through Google APIs. Already built and
  integrated; out of scope for this design. Treated as a black box with one input: project
  heading plus Drive link.
- Updates to existing projects are made on the sheet. Overwrite versus backup is deferred.

## Capability groups

| Group | Capabilities | Data source |
|---|---|---|
| Intake | WhatsApp group listener; broker portal download | WhatsApp, builder portals |
| Judge | Identify project, builder, city; classify document type; unbrand; quality check | The documents and the message around them |
| Act | Create Drive folders, upload, set sharing, register in portal | Google Drive, Realtor Portal |

## Decision

Not a new agent. Unbranding becomes a new capability of the existing Realtor Portal agentic
system; it is built there from this design.

v1 intake is a UI upload: staff upload the PDFs and enter metadata (project, builder, city).
The agent also extracts that metadata from the PDF itself where it can, so the form can be
pre-filled. Intake is an adapter, so a WhatsApp listener can be added later without changing
the pipeline. WhatsApp is deferred, not rejected.

Drive root and folder structure are configuration, not code.

Pipeline: intake → unbrand → file → share → publish. Broker portal download stays manual
in v1.

The unbranding step reuses the existing `unbrand-builder-docs` skill. Steps 3 to 5 are
deterministic code; a model is used only for identification, classification, unbranding and
quality check.

## Rejected

- Separate agents per step: steps share one document and one project identity; splitting adds
  hand-off loss (pattern 6) with no independent subtasks.
- Automating broker portal logins in v1: credential risk for a minority of documents.

## Open questions

1. WhatsApp listener (deferred): feasibility through an official channel, account-ban risk
   of unofficial libraries, which groups are watched. Needs a spike before it is built.
2. How staff identify project, builder and city today. To confirm with the team; decides
   how much the PDF extraction must carry.
3. Overwrite versus backup on updates (deferred by decision).
