-- The organization profile: who the agent works for and the mark it prints.
-- One row per deployment; with no row, the defaults in app/domain/organization.py
-- apply. Applied on first use, idempotently, like the other schema files.

CREATE TABLE IF NOT EXISTS organization (
  id         SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  profile    JSONB NOT NULL,
  updated_by TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
