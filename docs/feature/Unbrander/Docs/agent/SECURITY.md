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
- M2 runs in a sandbox with the document copy only.
- Their outputs are files and schema-validated JSON. Deterministic code reads these and
  does Drive and portal work.
- Public sharing and publishing happen only after a human approves.

Nothing written inside a PDF can cause an upload, a share or a publish.

## Sandbox (M2 code execution)

- Isolated container per document, deleted after the run.
- No network. No credentials or environment secrets mounted.
- Only the source PDF in; only the output PDF and a JSON report out.
- Limits: CPU and memory caps, 10-minute wall time, disk cap (for example 500 MB).
- Preinstalled tools only (`pymupdf`, `pdfplumber`, `reportlab`, `poppler`). Installing
  packages at run time is not allowed; this replaces the skill's `pip install` step.

## Access control

| Tool | Least privilege |
|---|---|
| Drive write | Service account with access to the configured Unbranded root only, not the whole Drive |
| Drive sharing change | Called only by the publish step, only for a job in `APPROVED` |
| Portal register | Existing portal integration; called only by the publish step |
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

- Drive service account key in the portal's secret store, never in a model context or the
  sandbox.
- If the key leaks: an attacker can read and change the Unbranded tree. Response: revoke and
  rotate the key, review the Drive activity log, restore from Drive version history.

---

## Operations

**Where it runs:** inside the Realtor Portal agentic system, as a job type on its queue.

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

1. Remove the portal entry.
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

1. Whether the portal already has a secret store and a job queue to reuse (assumed yes).
