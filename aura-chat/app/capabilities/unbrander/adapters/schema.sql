-- Unbrander's jobs: one project's PDFs on their way to a private Drive folder.
--
-- Applied on first use, idempotently, like chat's schema.sql: no Alembic. Later
-- phases add their columns here with ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS unbrander_jobs (
  id              TEXT PRIMARY KEY,
  -- RECEIVED | UNBRANDING | UNBRANDED | FILING | FILED_PRIVATE | FAILED. The worker reads it
  -- to know which step to run, so a restart resumes where the last run stopped.
  status          TEXT NOT NULL,
  uploader        TEXT NOT NULL,
  instructions    TEXT,
  project         TEXT NOT NULL,
  builder         TEXT NOT NULL,
  short_forms     JSONB NOT NULL DEFAULT '[]',
  city            TEXT NOT NULL,
  province        TEXT NOT NULL DEFAULT 'Ontario',
  -- The profile and brand this job was marked with. A copy, so a later edit of
  -- the profile does not change how a past output is explained.
  organization    JSONB NOT NULL,
  -- Filed under the test root. Publishing must refuse a dry-run job.
  dry_run         BOOLEAN NOT NULL,
  drive_folder_id TEXT,
  error           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Set on UNBRANDED, FILED_PRIVATE or FAILED, cleared when filing starts. Volume
  -- files are evicted counting from here.
  ended_at        TIMESTAMPTZ
);
-- File in Drive straight after unbranding (added with the admin app).
ALTER TABLE unbrander_jobs ADD COLUMN IF NOT EXISTS file_when_done BOOLEAN NOT NULL DEFAULT false;
-- The worker's question: the oldest job that has not ended.
CREATE INDEX IF NOT EXISTS unbrander_jobs_status ON unbrander_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS unbrander_documents (
  id            TEXT PRIMARY KEY,
  job_id        TEXT NOT NULL REFERENCES unbrander_jobs(id) ON DELETE CASCADE,
  position      INT  NOT NULL,
  filename      TEXT NOT NULL,
  sha256        TEXT NOT NULL,
  page_count    INT  NOT NULL,
  -- PENDING | UNBRANDING | VERIFIED | BLOCKED | FILED | FAILED. BLOCKED failed
  -- verify(): kept on the volume for the approver, never filed.
  status        TEXT NOT NULL,
  -- The most common kind among the pages the sort kept.
  doc_type      TEXT,
  dropped_pages JSONB NOT NULL DEFAULT '[]',
  removed_items JSONB NOT NULL DEFAULT '[]',
  findings      JSONB NOT NULL DEFAULT '[]',
  rounds        INT,
  usage         JSONB NOT NULL DEFAULT '{}',
  cost_usd      NUMERIC(10,4),
  -- Set once uploaded, so FILING skips it when a restart repeats the step.
  drive_file_id TEXT,
  -- The daily cap counts documents started today.
  started_at    TIMESTAMPTZ,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unbrander_documents_job ON unbrander_documents (job_id, position);
CREATE INDEX IF NOT EXISTS unbrander_documents_started ON unbrander_documents (started_at);

-- The audit log: one row per action, never updated (SECURITY.md). No cascade:
-- the log is kept after everything else about a job is gone.
CREATE TABLE IF NOT EXISTS unbrander_job_events (
  id          BIGSERIAL PRIMARY KEY,
  at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  job_id      TEXT NOT NULL REFERENCES unbrander_jobs(id),
  document_id TEXT,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  result      TEXT NOT NULL,
  detail      JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS unbrander_job_events_job ON unbrander_job_events (job_id, at);
