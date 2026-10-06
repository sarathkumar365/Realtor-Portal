# Phases 8 and 9 — Security and operations

Patterns applied: 18 to 21.
State: PROPOSED.

## Lethal trifecta

| Leg | Present? | Where |
|---|---|---|
| Private data | Yes | Drive (all projects), portal sheet, service credentials |
| Untrusted content | Yes | Builder PDFs: any text in them can be an instruction |
| Outbound action | Yes | Public link sharing, portal publish |

All three are present in the system, so they must never meet in one model context.

**Decision: the models that read PDFs have no outbound leg.**

- M1, M2 and M3 have no Drive, portal, sharing or network tools.
- M2 can only call the named PDF tools (LOOP.md), each scoped to the one document of its run.
  It has no code-execution tool, so PDF text cannot become code.
- Their outputs are files and schema-validated JSON. Deterministic code reads these and
  does Drive and portal work.
- Public sharing and publishing happen only after a human approves.

Nothing written inside a PDF can cause an upload, a share or a publish.

## No code execution (decision D3)

The model never writes or runs code, so no sandbox is built. The PDF tools are fixed Python
functions in Aura Chat:

- Each tool works on a temp copy of one document; the original upload is never modified.
- Tools take page numbers, rectangles and strings, never paths or URLs.
- Guards live in the tools (LOOP.md): no new words, no changed numbers, no near-full-page rects.
- Limits per document: 10-minute wall time, tool-call and render budgets (AUTONOMY.md).
- `pymupdf` and `reportlab` are installed with the service (D8). Neither needs system
  packages. `pymupdf` is AGPL-3.0: used **unmodified** in a service that is never
  distributed, its source obligations are not triggered. Patching it, or shipping the
  container to anyone, changes that; Artifex sells a commercial licence (price on request).
  The AGPL-free fallback is pypdfium2 + pikepdf with our own object-level redactor, which
  over-deletes around targets.

Rejected: the Claude API code-execution tool (no `pymupdf`, no runtime install) and a
self-built code sandbox on Railway (more to secure, no gain over named tools).

## Access control

| Tool | Least privilege |
|---|---|
| Upload screen and approval | Admin role only (decision D5); checked server-side from the session token |
| Drive write | Aura Chat `GoogleWriter` (D7), with a Google identity that can reach only the Unbranded tree and the sheet |
| Drive sharing change | Called only by the publish step, only for a job in `APPROVED` |
| Sheet write | Same `GoogleWriter`; code writes only the `UNBRANDED` cell of one row |
| Source uploads | Stored outside the public tree; never shared |

**Dry-run mode:** runs the pipeline up to `FILED_PRIVATE` into a separate test root; share and
publish are disabled. Default for a new configuration and for eval runs.

## Guardrails

Input (rejected before any model call, with a fixed message):

- Not a PDF (by content, not extension).
- Over 50 MB or over 60 pages (PROPOSED limits).
- Encrypted or password-protected.
- Contains JavaScript, embedded files or launch actions → strip, or reject if stripping fails.

Output (must pass before `FILED_PRIVATE`):

- Leak guard: text and metadata sweep (see AUTONOMY.md).
- Invented-content guard: word provenance and number integrity.
- Metadata guard: document info, XMP, links, annotations, embedded files cleared.

## Credentials

- **A Google service account is held by Aura Chat** (D7, D17). Its JSON key is a Railway
  environment variable, never in a model context or on the volume.
  - The Unbranded tree lives in a **Shared Drive**; the service account is a member of that
    Shared Drive only (Content manager: it can create, upload and share, not delete the
    drive).
  - The sheet is shared with the service account as **Editor**. Code writes only the
    `UNBRANDED` cell of one row.
  - No domain-wide delegation: it can reach nothing that is not shared with it.
  - Rejected: a dedicated Workspace user with an OAuth refresh token (a paid seat, and a
    token that breaks when the account's password or policy changes).
- If the credential leaks: an attacker can change the Unbranded tree and the sheet. Response:
  revoke the key or token, review the Drive and sheet activity logs, restore from version
  history.
- Anthropic API key: Railway environment variable, as today.

---

## Operations

**Where it runs:** inside Aura Chat on Railway. Jobs are rows in the Postgres `jobs` table;
a worker in the same service claims them (`FOR UPDATE SKIP LOCKED`).

**Trigger:** a UI upload creates a job. Later, a WhatsApp adapter creates the same job.

**Logging:** every action writes an audit entry:

```
timestamp, job_id, document_id, step, actor (agent | user id), action,
reason, input_sha256, output reference, result
```

Model calls also log the model, prompt version, token count and cost.

**Stop:**

- Global switch `unbrander.enabled` in configuration. When off, new jobs queue and nothing
  publishes.
- Per-job cancel in the UI, at any state before `PUBLISHED`.

**Undo a publish (one action in the UI):**

1. Restore the `UNBRANDED` cell to its previous value (empty, or the old link).
2. Remove the "anyone with the link" permission.
3. Move the output files to Drive trash (never hard-delete).
4. Return the job to `AWAITING_APPROVAL` with the reason.

**Retention:** keep source PDFs and outputs for the life of the project, so any published
file can be traced back to its original.

**Alerts to the operator:** job in `FAILED`, a reported leak, daily cap reached, eval gate
failed.

## Configuration

```
unbrander.enabled
drive.unbranded_root_folder_id
drive.test_root_folder_id
drive.province_default            ("Ontario")
drive.cities[]                    (allowed city folders)
drive.subfolders.floor_plans      ("Floor Plans")
limits.max_file_mb, limits.max_pages, limits.docs_per_day, limits.doc_timeout_min
intake.adapters[]                 (["ui"]; "whatsapp" later)
```

## Open questions

Settled 2026-10-05/06: service account + Shared Drive; queue is Postgres; writes direct from Aura Chat; files on a Railway volume; PyMuPDF and reportlab;
secrets are Railway environment variables and Script Properties, as today.
