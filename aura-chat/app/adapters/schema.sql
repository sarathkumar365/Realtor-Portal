-- Aura Chat's own storage. Conversations and things derived from them, never a
-- copy of project data: cards are re-rendered from live Sheets at read time, so
-- a conversation reopened next month shows this month's price.
--
-- Applied on startup, idempotently. No Alembic: three tables in a sprint did not
-- justify the dependency or the workflow. The cost is real -- no rollback, and
-- every later change is hand-written here.

CREATE TABLE IF NOT EXISTS ai_conversations (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  title      TEXT NOT NULL DEFAULT '',
  -- AUR-57. Stored so a reopened conversation comes back in the mode it was
  -- held in, rather than in whatever the phone happened to be showing.
  mode       TEXT NOT NULL DEFAULT 'realtor',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Every list is "this realtor's conversations, newest first", and user_id leads
-- because it is also the isolation filter (AUR-40).
CREATE INDEX IF NOT EXISTS ai_conversations_user
  ON ai_conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS ai_messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL,
  message         TEXT NOT NULL,
  -- [{"id","name"}] of the projects the answer was built from. This is the
  -- compare-by-name fix: without it a follow-up has names and no ids, and the
  -- model invents them. See known-issues 4 and domain/conversation.source_line.
  sources         JSONB NOT NULL DEFAULT '[]',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_messages_conv
  ON ai_messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS feedback (
  id          TEXT PRIMARY KEY,
  -- The client's answer_id. Deliberately NOT a foreign key to ai_messages yet:
  -- message ids are server-minted from now on, but installed phones still send
  -- their own, and a constraint would reject every report from a phone that has
  -- not updated. Add it once the rollout completes.
  message_id  TEXT,
  user_id     TEXT NOT NULL,
  question    TEXT NOT NULL,
  -- Nullable: a thumb judges the ANSWER, a data issue reports the SHEET, and a
  -- well-sourced answer can quote a stale price. Filing every AUR-60 report as
  -- a thumbs-down would corrupt the AUR-59 helpfulness rate.
  verdict     TEXT,
  category    TEXT,
  note        TEXT NOT NULL DEFAULT '',
  project_ids JSONB NOT NULL DEFAULT '[]',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Sudhanshu works the queue newest-first, across all users.
CREATE INDEX IF NOT EXISTS feedback_created ON feedback (created_at DESC);
