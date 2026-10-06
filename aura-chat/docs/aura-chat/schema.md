# Aura Chat — database schema

Three tables, on Railway Postgres. AUR-88.

Source of truth is [`../../aura-chat/app/adapters/schema.sql`](../../aura-chat/app/adapters/schema.sql),
applied at startup on every boot. It is idempotent (`CREATE TABLE IF NOT EXISTS`),
so restarts and replicas are safe. **There is no migration tool** — see
[worklog](../worklog.md) for why, and what it costs.

## What is here, and what is deliberately not

This database holds **conversations and things derived from them**. It holds no
project data, ever. Cards are re-rendered from live Sheets at read time, so a
conversation reopened next month shows next month's price rather than the price
that was quoted when it was asked. Mirroring Sheets here is a documented future
option ([architecture.md](architecture.md) §4.3) and is not this.

## `ai_conversations`

One thread. AUR-36.

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT` PK | UUID, server-minted |
| `user_id` | `TEXT` | The portal username from the verified token. **The isolation key.** |
| `title` | `TEXT` | The first question, truncated to 60 — what a realtor recognises in a list |
| `mode` | `TEXT` | `realtor` or `client`. AUR-57: a reopened thread comes back in the mode it was held in |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `updated_at` moves on every append, in the same transaction |

Indexed `(user_id, updated_at DESC)` — every list is "this realtor's threads,
newest first", and `user_id` leads because it is also the isolation filter.

## `ai_messages`

One turn. AUR-37.

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT` PK | UUID |
| `conversation_id` | `TEXT` FK | `ON DELETE CASCADE` |
| `role` | `TEXT` | `user` or `assistant` |
| `message` | `TEXT` | What was said. Not the cards |
| `sources` | `JSONB` | `[{"id","name"}]` — the projects the answer was built from |
| `created_at` | `TIMESTAMPTZ` | |

`id` and `created_at` come back out of `history()` as well as going in. The model
never sees either — `turns_from` builds `Turn(role, content)` and nothing else —
but the history panel does: `auraFeedbackRow` returns nothing for a turn with no
id rather than offer a vote it cannot attribute, so a reopened answer without one
would silently have no thumbs.

**`sources` is the point of this table.** History reaches the model as prose, so
a previous answer tells it the *names* of projects and not their ids; asked to
"compare the first two" it invents plausible ones and the lookup fails
([known-issues 4](known-issues.md)). `domain.conversation.turns_from` appends the
ids as one line when rebuilding history, and the model can then refer to
something real.

It is capped at 12 entries per turn: `Deps.collected` accumulates across every
tool call in a run, so a six-search answer can carry far more projects than it
named.

## `feedback`

One report. The storage half of AUR-61.

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT` PK | UUID |
| `message_id` | `TEXT` | The client's `answer_id`. **Not a foreign key yet** — see below |
| `user_id` | `TEXT` | From the token, never the body |
| `question` | `TEXT` | Capped at 500 |
| `verdict` | `TEXT` | `up`, `down`, **or null** |
| `category` | `TEXT` | One of the seven AUR-60 categories, or null |
| `note` | `TEXT` | Capped at 200 |
| `project_ids` | `JSONB` | Which projects the report is about |
| `created_at` | `TIMESTAMPTZ` | Indexed `DESC` — the queue is worked newest first |

**`verdict` is nullable on purpose.** A thumb judges the *answer* (AUR-59); a
data issue reports the *sheet* (AUR-60), and a well-sourced answer can quote a
stale price through no fault of its own. Filing every data issue as a
thumbs-down would have made the helpfulness rate untrustworthy. A row carries at
least one of verdict, category or note — the model refuses the rest.

**`message_id` has no foreign key** because message ids are server-minted from
now on, but installed phones still send their own `answer_id`, and a constraint
would reject every report from a phone that has not updated. Add it once the
rollout completes.

**The answer text is not stored here.** It can quote commission in Realtor Mode.
Once `ai_messages` is populated everywhere, `message_id` joins to it and the
reviewer sees the answer without it being duplicated into the feedback row.

## Isolation (AUR-40)

Every read that can reach a conversation takes `user` and filters on it **in the
SQL**. A `conversation_id` is a label, not a capability: it appears in URLs, logs
and browser history, and opens nothing on its own.

- `history()` returns `[]` for a conversation this user does not own
- `meta()` returns `None` — it answers both questions a caller has about a
  thread it did not just create, may I write to it and what mode was it held in,
  in one round trip. It is checked separately from `history()` because an empty
  conversation is a real state and it belongs to somebody
- `set_mode()` carries `user` in the `WHERE` too, so a borrowed id cannot change
  another realtor's stored mode
- `/conversations/{id}` answers **404 with the same body** for "not yours" and
  "does not exist"; distinguishing them is itself a disclosure
- an id that is **not the caller's is not an error on the write path** — `/chat`
  ignores it and starts a fresh conversation, so a client holding a stale id
  (the next realtor on a shared phone) keeps working rather than losing
  persistence silently

Proven against real Postgres, not just the fake, by
[`scripts/check_store.py`](../../aura-chat/scripts/check_store.py) and
[`scripts/check_chat_persistence.py`](../../aura-chat/scripts/check_chat_persistence.py).

## Running the checks

```bash
cd aura-chat && createdb aura_chat_dev
DATABASE_URL=postgresql://$USER@localhost/aura_chat_dev .venv/bin/python scripts/check_store.py
DATABASE_URL=postgresql://$USER@localhost/aura_chat_dev .venv/bin/python scripts/check_chat_persistence.py
```

Both mint unique user names per run, so they are safe to re-run and safe to run
against the same database as each other.

## Retention

Everything is kept. There is no expiry job and no delete path.

## When the database is unreachable

History degrades; nothing else does. `/chat` falls back to the turns the client
sends, `/feedback` still writes its audit line, `/health` stays up, and both
`/conversations` routes answer **503 with the same wording as when no database
is configured** — a realtor cannot act on the difference.

## Backup and restore (AUR-92)

**What has to be backed up: this database, and nothing else.** Project records
are not here and never will be — the Sheets are the source of truth for those,
and Google backs them up. What lives only here is conversations, messages and
the feedback queue: if this is lost, every reported data issue is lost with it,
and those are the queue Sudhanshu works from.

Everything else is reproducible from the repo: `schema.sql` rebuilds the tables
on boot, and the service is a redeploy.

### Taking one

Railway's Postgres is on the private network, so a dump runs from inside the
project rather than from a laptop:

```bash
railway run --service aura-chat pg_dump "$DATABASE_URL" -Fc -f aura-$(date +%F).dump
```

`-Fc` is the custom format — compressed, and restorable table by table. A plain
`.sql` dump also works and is easier to read, which matters more than size at
this volume (~30 MB a year).

There is no schedule. At twenty realtors and one sprint of data that is a
defensible choice and a deliberate one; **before this carries a quarter of
reports, turn on Railway's own backups** rather than relying on somebody
remembering the command.

### Putting one back

```bash
railway run --service aura-chat pg_restore -d "$DATABASE_URL" --clean --if-exists aura-2026-08-25.dump
```

`--clean --if-exists` drops what it is replacing, so it overwrites rather than
merges. Restoring into a database the service is still writing to will lose the
writes in between — redeploy with the service stopped, or accept the gap.

The schema needs no separate step either way: it is applied on every boot and is
idempotent, so a restore into an empty database and a restore over a live one
both end up correct.

### What a restore does not fix

`feedback.message_id` is still a client-minted `answer_id` with no foreign key,
so a restored report points at an answer only by coincidence of the same string.
That is the same before and after a restore — see the note on the `feedback`
table above — but it is worth knowing before trying to join the two.
