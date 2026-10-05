"""Chat persistence end to end: real routes, real SSE, real Postgres.

Only the model is faked. Everything else is the shipping path -- which is the
point: the pytest suite proves this against a fake store, and a fake store is
exactly where an isolation bug would hide.

Not a pytest, for the same reason as check_store.py: the suite must never need a
database, and a test that skips when one is absent stops being noticed.

    DATABASE_URL=postgresql://localhost/aura_chat_dev \\
      .venv/bin/python scripts/check_chat_persistence.py
"""

import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from fastapi.testclient import TestClient

from app.adapters.store_postgres import PostgresConversationStore
from app.config import Settings
from app.container import Container
from app.domain import Claims, Role
from app.main import create_app
from tests.conftest import StubPortal
from tests.fakes import TEST_SECRET, FakeAuthVerifier, FakeProjectRepo, make_token

fails = 0

# Unique per run: this script and check_store.py share a database, and a fixed
# user name means one script's leftovers fail the other's isolation check.
RUN = uuid.uuid4().hex[:8]
MINE, THEIRS = f"sarath-{RUN}", f"priya-{RUN}"


def ok(cond: bool, msg: str) -> None:
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        fails += 1


class StubRuntime:
    """Answers with two Oakville townhomes, so the follow-up has something to
    refer to. `seen` captures what the runtime was handed."""

    def __init__(self) -> None:
        self.seen: dict = {}

    async def stream(self, **kw):
        self.seen = kw
        yield {"type": "text", "text": "Two Oakville townhomes match."}
        yield {"type": "projects", "projects": [
            {"id": "AK-0021", "name": "Ivy Rogue"},
            {"id": "AK-0022", "name": "New Kleinburg"},
        ]}
        yield {"type": "done"}

    async def healthy(self) -> bool:
        return True


def events(text: str) -> list[dict]:
    return [json.loads(ln[6:]) for ln in text.splitlines() if ln.startswith("data: ")]


async def _reassign(dsn: str, conversation_id: str, user: str) -> None:
    con = await asyncpg.connect(dsn)
    await con.execute(
        "UPDATE ai_conversations SET user_id = $1 WHERE id = $2", user, conversation_id
    )
    await con.close()


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2

    cfg = Settings(
        token_secret=TEST_SECRET, exec_url="https://example.invalid/exec",
        database_url=dsn, _env_file=None,
    )
    app = create_app(cfg)
    runtime = StubRuntime()
    app.state.container = Container(
        settings=cfg, portal=StubPortal(), auth=FakeAuthVerifier(Claims(user=MINE, role=Role.REALTOR, issued_ms=0)),
        projects=FakeProjectRepo([]), runtime=runtime,
        store=PostgresConversationStore(dsn),
    )
    head = {"Authorization": f"Bearer {make_token(MINE)}"}

    with TestClient(app) as client:
        first = client.post(
            "/chat", json={"question": "What townhomes are in Oakville?"}, headers=head
        )
        cid = events(first.text)[0]["conversation_id"]
        ok(cid is not None, "a question creates a conversation in real Postgres")

        stored = client.get(f"/conversations/{cid}", headers=head).json()["messages"]
        ok([m["role"] for m in stored] == ["user", "assistant"], "both turns persisted")
        ok(stored[1]["sources"] == [
            {"id": "AK-0021", "name": "Ivy Rogue"}, {"id": "AK-0022", "name": "New Kleinburg"}],
            "the ids from the projects event survived the JSONB round trip")

        # The reason the phase exists (known-issues 4).
        client.post(
            "/chat",
            json={"question": "Compare the first two.", "conversation_id": cid},
            headers=head,
        )
        context = "\n".join(t.content for t in runtime.seen["history"])
        ok("AK-0021 Ivy Rogue" in context, "the follow-up's model context carries the real ids")
        ok("oakville-townhomes" not in context, "nothing invented")

        ok(client.get("/conversations", headers=head).json()["conversations"][0]["id"] == cid,
           "the thread lists for its owner, newest first")

        # AUR-40 over real SQL. Not by swapping tokens -- FakeAuthVerifier answers
        # the same user for any token, so a token swap would prove nothing. The
        # row genuinely belongs to somebody else.
        second = events(client.post("/chat", json={"question": "hi"}, headers=head).text)
        hers = second[0]["conversation_id"]
        asyncio.run(_reassign(dsn, hers, THEIRS))
        ok(client.get(f"/conversations/{hers}", headers=head).status_code == 404,
           "a conversation owned by another realtor is a 404")
        refused = events(
            client.post("/chat", json={"question": "x", "conversation_id": hers}, headers=head).text
        )
        fresh = refused[0]["conversation_id"]
        ok(fresh is not None and fresh != hers,
           "an id that is not ours is refused and a fresh conversation started")
        theirs_rows = client.get(f"/conversations/{hers}", headers=head)
        ok(theirs_rows.status_code == 404, "and hers stays closed to us")
        ok(len(client.get(f"/conversations/{fresh}", headers=head).json()["messages"]) >= 1,
           "the question landed in ours, not nowhere")

    print("\n" + ("ALL CHECKS PASSED" if not fails else f"{fails} CHECK(S) FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
