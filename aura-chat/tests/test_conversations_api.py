"""Reading conversations back, and above all not reading somebody else's.

AUR-40 is the reason this file exists. A conversation_id is a label, not a
capability: it appears in a URL, it will end up in a log and a browser history,
and it must open nothing on its own.
"""

from fastapi.testclient import TestClient

from tests.fakes import FakeConversationStore, FakeProjectRepo, make_token

MINE = make_token("sarath")
THEIRS = make_token("priya")


def wire(app, store=None):
    app.state.container.store = store or FakeConversationStore()
    app.state.container.projects = FakeProjectRepo([])
    return app.state.container.store


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_listing_requires_a_token(app):
    wire(app)
    with TestClient(app) as client:
        assert client.get("/conversations").status_code == 401


def test_a_realtor_sees_their_own_threads(app):
    store = wire(app)
    cid = _run(store.create(user="sarath", title="Brampton townhomes"))
    with TestClient(app) as client:
        body = client.get("/conversations", headers=auth(MINE)).json()
    assert [c["id"] for c in body["conversations"]] == [cid]
    assert body["conversations"][0]["title"] == "Brampton townhomes"


def test_another_realtors_threads_are_not_listed(app):
    """The list is the easy half of isolation and still worth pinning: a missing
    WHERE user_id would show the whole brokerage's conversations to everyone."""
    store = wire(app)
    _run(store.create(user="priya", title="Oakville detached"))
    with TestClient(app) as client:
        body = client.get("/conversations", headers=auth(MINE)).json()
    assert body["conversations"] == []


def test_a_borrowed_conversation_id_is_a_404(app):
    """The hard half. priya's id is valid, exists, and has messages in it --
    sarath presenting it must get exactly what he would get for an id that never
    existed, because distinguishing the two is itself a disclosure."""
    store = wire(app)
    cid = _run(store.create(user="priya", title="Oakville detached"))
    _run(store.append(conversation_id=cid, role="user", message="what is the commission?"))
    with TestClient(app) as client:
        r = client.get(f"/conversations/{cid}", headers=auth(MINE))
        missing = client.get("/conversations/does-not-exist", headers=auth(MINE))
    assert r.status_code == 404
    assert r.status_code == missing.status_code
    assert r.json() == missing.json()          # not even the wording differs
    assert "commission" not in r.text


def test_the_owner_reads_their_messages(app):
    store = wire(app)
    cid = _run(store.create(user="sarath", title="Brampton"))
    _run(store.append(conversation_id=cid, role="user", message="townhomes in Brampton?"))
    _run(store.append(
        conversation_id=cid, role="assistant", message="Two match.",
        sources=[{"id": "AK-1", "name": "Duo"}],
    ))
    with TestClient(app) as client:
        body = client.get(f"/conversations/{cid}", headers=auth(MINE)).json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["sources"][0]["id"] == "AK-1"


def test_the_stored_rows_are_returned_not_the_model_facing_turns(app):
    """turns_from appends "[projects: ...]" for the model to read. A realtor
    reopening a thread must not see it in the answer."""
    store = wire(app)
    cid = _run(store.create(user="sarath", title="x"))
    _run(store.append(
        conversation_id=cid, role="assistant", message="Two match.",
        sources=[{"id": "AK-1", "name": "Duo"}],
    ))
    with TestClient(app) as client:
        body = client.get(f"/conversations/{cid}", headers=auth(MINE)).json()
    assert body["messages"][0]["message"] == "Two match."
    assert "[projects:" not in body["messages"][0]["message"]


def test_no_store_is_a_503_not_a_500(app):
    """Nothing is broken -- the feature is not configured. Chat keeps working."""
    app.state.container.store = None
    app.state.container.projects = FakeProjectRepo([])
    with TestClient(app) as client:
        assert client.get("/conversations", headers=auth(MINE)).status_code == 503


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def test_a_down_store_degrades_rather_than_500s(app):
    """A database blip used to give a realtor working answers next to a history
    panel throwing a stack trace. "Not configured" and "unreachable" are the
    same sentence to them -- history is unavailable -- so they answer alike."""
    store = wire(app)
    store.up = False
    with TestClient(app, raise_server_exceptions=False) as client:
        listed = client.get("/conversations", headers=auth(MINE))
        one = client.get("/conversations/anything", headers=auth(MINE))
    assert listed.status_code == 503
    assert one.status_code == 503
    assert listed.json()["detail"] == one.json()["detail"]


def test_an_unconfigured_and_an_unreachable_store_read_the_same(app):
    """Same wording either way: a realtor cannot act on the difference, and the
    detail string is what they see."""
    store = wire(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        store.up = False
        unreachable = client.get("/conversations", headers=auth(MINE)).json()["detail"]
    app.state.container.store = None
    with TestClient(app) as client:
        unconfigured = client.get("/conversations", headers=auth(MINE)).json()["detail"]
    assert unreachable == unconfigured


# ---- AUR-57 and the two things the 4b history panel needs ------------------

def test_a_thread_comes_back_with_the_mode_it_was_held_in(app):
    """The client applies this before painting a word. Without it a Client Mode
    conversation reopens under a realtor-blue header and switches a moment
    later -- which is the one thing that header exists to prevent."""
    store = wire(app)
    cid = _run(store.create(user="sarath", title="for a buyer", mode="client"))
    with TestClient(app) as client:
        body = client.get(f"/conversations/{cid}", headers=auth(MINE)).json()
    assert body["mode"] == "client"
    assert body["title"] == "for a buyer"


def test_reopened_turns_carry_their_ids(app):
    """auraFeedbackRow returns null without one, so an id-less answer silently
    loses its feedback buttons on reopen."""
    store = wire(app)
    cid = _run(store.create(user="sarath", title="t"))
    _run(store.append(conversation_id=cid, role="user", message="hi"))
    _run(store.append(conversation_id=cid, role="assistant", message="hello"))
    with TestClient(app) as client:
        msgs = client.get(f"/conversations/{cid}", headers=auth(MINE)).json()["messages"]
    assert all(m["id"] for m in msgs)
    assert all(m["created_at"] for m in msgs)


def test_reading_a_thread_asks_for_more_than_the_model_window(app):
    """history() defaults to 20 because that is what fits in a prompt. A realtor
    reopening a long conversation wants to scroll all of it."""
    from app.conversations import MAX_MESSAGES

    seen = {}

    class Recording(FakeConversationStore):
        async def history(self, *, conversation_id, user, limit=20):
            seen["limit"] = limit
            return await super().history(conversation_id=conversation_id, user=user, limit=limit)

    store = wire(app, Recording())
    cid = _run(store.create(user="sarath", title="t"))
    with TestClient(app) as client:
        client.get(f"/conversations/{cid}", headers=auth(MINE))
    assert seen["limit"] == MAX_MESSAGES > 20


def test_continuing_a_thread_in_another_mode_updates_it(app):
    """Otherwise the stored mode is whatever the first question used, and the
    list badges a client conversation as a realtor one."""
    from tests.test_chat_endpoint import StubRuntime

    store = wire(app)
    app.state.container.runtime = StubRuntime()
    cid = _run(store.create(user="sarath", title="t", mode="realtor"))
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={"question": "hi", "mode": "client", "conversation_id": cid},
            headers=auth(MINE),
        )
    assert _run(store.meta(conversation_id=cid, user="sarath"))["mode"] == "client"


def test_a_borrowed_id_cannot_change_another_realtors_mode(app):
    """The stale-id path creates a fresh conversation; it must not reach into
    the one the id names."""
    from tests.test_chat_endpoint import StubRuntime

    store = wire(app)
    app.state.container.runtime = StubRuntime()
    theirs = _run(store.create(user="priya", title="t", mode="realtor"))
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={"question": "hi", "mode": "client", "conversation_id": theirs},
            headers=auth(MINE),
        )
    assert _run(store.meta(conversation_id=theirs, user="priya"))["mode"] == "realtor"


def test_a_failed_mode_update_does_not_cost_the_conversation(app):
    """The only write on a path that used to be all reads. Letting it escape
    sent back a null conversation_id, the client dropped the id it held, and the
    next question opened a second thread with none of the context."""
    from tests.test_chat_endpoint import StubRuntime, sse

    class ModeWriteFails(FakeConversationStore):
        async def set_mode(self, **kw):
            raise RuntimeError("deadlock detected")

    store = wire(app, ModeWriteFails())
    app.state.container.runtime = StubRuntime()
    cid = _run(store.create(user="sarath", title="t", mode="realtor"))
    with TestClient(app) as client:
        r = client.post(
            "/chat",
            json={"question": "hi", "mode": "client", "conversation_id": cid},
            headers=auth(MINE),
        )
    start = sse(r.text)[0]
    assert start["conversation_id"] == cid, "the client must keep the thread it had"
    # And the answer still landed in it.
    assert [m["role"] for m in _run(store.history(conversation_id=cid, user="sarath"))] == [
        "user",
        "assistant",
    ]


def test_a_phone_that_sends_no_conversation_id_keeps_its_context(app):
    """The body fallback was unreachable: a new conversation is empty, so
    returning stored turns unconditionally discarded what the client sent."""
    from tests.test_chat_endpoint import StubRuntime

    wire(app)
    rt = StubRuntime()
    app.state.container.runtime = rt
    sent = [
        {"role": "user", "content": "detached in Brampton"},
        {"role": "assistant", "content": "Arbor West and Credit Manor"},
    ]
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={"question": "compare the first two", "history": sent},
            headers=auth(MINE),
        )
    assert [t.content for t in rt.seen["history"]] == [t["content"] for t in sent]


def test_stored_turns_still_win_once_the_thread_has_any(app):
    """The body is the phone asserting what was said; the store knows. A client
    that sends both must not be able to rewrite the thread."""
    from tests.test_chat_endpoint import StubRuntime

    store = wire(app)
    rt = StubRuntime()
    app.state.container.runtime = rt
    cid = _run(store.create(user="sarath", title="t"))
    _run(store.append(conversation_id=cid, role="user", message="what is real"))
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={
                "question": "next",
                "conversation_id": cid,
                "history": [{"role": "user", "content": "invented"}],
            },
            headers=auth(MINE),
        )
    contents = [t.content for t in rt.seen["history"]]
    assert "what is real" in contents
    assert "invented" not in contents


def test_a_failed_question_write_still_leaves_the_answer_in_the_thread(app):
    """A created conversation that loses its first write must not survive with a
    title and no messages -- it lists as a thread that opens empty."""
    from tests.test_chat_endpoint import StubRuntime, sse

    class FirstAppendFails(FakeConversationStore):
        def __init__(self):
            super().__init__()
            self.tries = 0

        async def append(self, **kw):
            self.tries += 1
            if self.tries == 1:
                raise RuntimeError("pool timeout")
            return await super().append(**kw)

    store = wire(app, FirstAppendFails())
    app.state.container.runtime = StubRuntime()
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "hi"}, headers=auth(MINE))
    cid = sse(r.text)[0]["conversation_id"]
    assert cid is not None, "the client must still learn the conversation it is in"
    rows = _run(store.history(conversation_id=cid, user="sarath"))
    assert [m["role"] for m in rows] == ["assistant"], "the answer still lands"
