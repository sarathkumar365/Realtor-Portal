"""Exercise the real Postgres adapter against a real database.

Deliberately NOT a pytest: the suite must never need a database, and a test that
quietly skips when one is absent is a test nobody notices has stopped running.
This is a one-shot you run by hand, and it prints what it proved.

    DATABASE_URL=postgresql://localhost/aura_chat_dev .venv/bin/python scripts/check_store.py
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.adapters.store_postgres import PostgresConversationStore
from app.domain import turns_from

OK, BAD = "  ok  ", "  FAIL"
fails = 0

# Users are unique per run. The first version reused "sarath" and "priya", so a
# re-run -- or a run of the other script, which shares this database -- left rows
# behind that made "and not in anybody else's" fail against correct code. A check
# that only passes on a clean database is a check that will cry wolf.
RUN = uuid.uuid4().hex[:8]
MINE, THEIRS = f"sarath-{RUN}", f"priya-{RUN}"


def ok(cond: bool, msg: str) -> None:
    global fails
    print((OK if cond else BAD) + "  " + msg)
    if not cond:
        fails += 1


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    store = PostgresConversationStore(dsn)

    # Applied on every boot, so it has to survive being applied twice.
    await store._ready()
    store._pool = None
    await store._ready()
    ok(True, "schema.sql applies twice without error (every boot re-runs it)")

    cid = await store.create(user=MINE, title="Brampton townhomes")
    await store.append(conversation_id=cid, role="user", message="townhomes in Brampton?")
    await store.append(
        conversation_id=cid, role="assistant", message="Two match.",
        sources=[{"id": "AK-1", "name": "Duo"}, {"id": "AK-2", "name": "Reva"}],
    )

    rows = await store.history(conversation_id=cid, user=MINE)
    ok([r["role"] for r in rows] == ["user", "assistant"], "both turns come back, oldest first")
    ok(rows[1]["sources"][0]["id"] == "AK-1", "sources survive the JSONB round trip")

    turns = turns_from(rows)
    ok("AK-1 Duo" in turns[-1].content, "the model would see the ids (the compare fix)")

    # AUR-40, against the real SQL rather than the fake.
    ok(await store.history(conversation_id=cid, user=THEIRS) == [],
       "another realtor reading the same id gets nothing")
    ok(await store.meta(conversation_id=cid, user=THEIRS) is None,
       "another realtor cannot write into it either")
    ok(await store.meta(conversation_id=cid, user=MINE) is not None, "the owner can")

    ok(all(r.get("id") for r in rows), "every stored turn comes back with its id")
    ok(all(r.get("created_at") for r in rows), "and with when it was said")

    # AUR-57: the mode a thread is held in, round-tripped through real SQL.
    ok((await store.meta(conversation_id=cid, user=MINE))["mode"] == "realtor",
       "a thread remembers the mode it was created in")
    await store.set_mode(conversation_id=cid, user=MINE, mode="client")
    ok((await store.meta(conversation_id=cid, user=MINE))["mode"] == "client",
       "and follows the mode it is continued in")
    await store.set_mode(conversation_id=cid, user=THEIRS, mode="realtor")
    ok((await store.meta(conversation_id=cid, user=MINE))["mode"] == "client",
       "another realtor cannot change it -- user is in the WHERE, not just the read")
    await store.set_mode(conversation_id=cid, user=MINE, mode="realtor")

    listed = await store.list_for(user=MINE)
    ok(any(c["id"] == cid for c in listed), "it appears in the owner's list")
    ok(await store.list_for(user=THEIRS) == [], "and not in anybody else's")

    await store.record_feedback(user=MINE, entry={
        "answer_id": "a-1", "question": "q", "verdict": "down",
        "category": "price_incorrect", "note": "stale", "project_ids": ["AK-1"],
    })
    fb = await store.list_feedback(limit=5)
    ok(fb and fb[0]["category"] == "price_incorrect", "feedback lands in the queue")
    ok(fb[0]["project_ids"] == ["AK-1"], "project ids survive as a list")

    ok(await store.healthy() is True, "healthy() answers true against a live database")

    # Ordering is what the history list is for -- a realtor finds the thread they
    # were just in at the top.
    other = await store.create(user=MINE, title="Oakville")
    await store.append(conversation_id=other, role="user", message="later")
    ok((await store.list_for(user=MINE))[0]["id"] == other,
       "the most recently touched conversation sorts first")

    await store.aclose()
    print(f"\n{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
