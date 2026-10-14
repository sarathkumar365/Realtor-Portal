"""The SSE contract the PWA will consume."""

import json

from fastapi.testclient import TestClient

from app.domain import ChatMode, Project
from tests.fakes import FakeProjectRepo, make_token

TOKEN = make_token("sarath")


class StubRuntime:
    def __init__(self, events=None):
        self.events = events or [{"type": "text", "text": "hi"}, {"type": "done"}]
        self.seen: dict = {}

    async def stream(self, *, question, claims, auth, mode, repo, history=None):
        self.seen = {
            "question": question, "mode": mode, "auth": auth,
            "repo": repo, "history": history or [],
        }
        for e in self.events:
            yield e

    async def healthy(self):
        return True


def wire(app, runtime=None, projects=None):
    app.state.container.runtime = runtime or StubRuntime()
    app.state.container.projects = FakeProjectRepo(projects or [Project(name="R", city="C")])
    return app.state.container.runtime


def sse(text: str) -> list[dict]:
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_chat_requires_a_token(app):
    wire(app)
    with TestClient(app) as client:
        assert client.post("/chat", json={"question": "hi"}).status_code == 401


def test_chat_streams_events(app):
    wire(app)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    kinds = [e["type"] for e in sse(r.text)]
    assert kinds[0] == "start" and kinds[-1] == "done"


def test_the_mode_is_echoed_before_any_content(app):
    """A realtor must never wonder whether the screen they just turned around
    is safe, so the answer states its mode before it says anything else."""
    wire(app)
    with TestClient(app) as client:
        r = client.post(
            "/chat",
            json={"question": "hi", "mode": "client"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    first = sse(r.text)[0]
    assert first["type"] == "start"
    assert first["mode"] == "client"
    # Rides along so a new chat learns its own id without a second request.
    # None here because this app has no store wired.
    assert first["conversation_id"] is None


def test_the_runtime_is_handed_a_repo_narrowed_to_the_viewer(app):
    """The client sends the mode, but nothing downstream trusts it with more
    than choosing a Viewer: the repo is built here and the agent cannot widen
    it."""
    rt = wire(app, projects=[Project(name="R", city="C", commission="4%")])
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={"question": "hi", "mode": "client"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    from app.adapters.projects_redacting import RedactingProjectRepo

    assert isinstance(rt.seen["repo"], RedactingProjectRepo)
    assert rt.seen["mode"] is ChatMode.CLIENT


def test_an_unconfigured_model_says_so_rather_than_500ing(app):
    wire(app)
    app.state.container.runtime = None
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert sse(r.text)[0]["type"] == "error"


def test_an_unconfigured_repo_streams_an_error_rather_than_500ing(app):
    """The same class of misconfiguration as a missing runtime, so the client
    must see the same shape -- not an HTML 500 where it expected an event
    stream."""
    wire(app)
    app.state.container.projects = None
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert sse(r.text)[0]["type"] == "error"


def test_a_runtime_that_raises_still_ends_in_an_error_event(app):
    """The port promises an iterator of events, not that it never raises."""

    class Exploding(StubRuntime):
        async def stream(self, **kw):
            yield {"type": "text", "text": "partial"}
            raise RuntimeError("upstream died")

    wire(app, runtime=Exploding())
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert [e["type"] for e in sse(r.text)][-1] == "error"


def test_an_empty_question_is_refused(app):
    wire(app)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": ""}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 422


def test_a_very_long_question_is_refused(app):
    wire(app)
    with TestClient(app) as client:
        r = client.post(
            "/chat", json={"question": "x" * 5000}, headers={"Authorization": f"Bearer {TOKEN}"}
        )
    assert r.status_code == 422


def test_history_is_passed_through_to_the_runtime(app):
    rt = wire(app)
    with TestClient(app) as client:
        client.post(
            "/chat",
            json={
                "question": "only detached",
                "history": [
                    {"role": "user", "content": "projects in Brampton"},
                    {"role": "assistant", "content": "Here are 11."},
                ],
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert [t.content for t in rt.seen["history"]] == ["projects in Brampton", "Here are 11."]


def test_an_overlong_history_is_refused(app):
    """A cap, so the prompt cannot grow without bound one refinement at a time."""
    wire(app)
    turns = [{"role": "user", "content": "x"}] * 50
    with TestClient(app) as client:
        r = client.post(
            "/chat",
            json={"question": "hi", "history": turns},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert r.status_code == 422


# ---- persistence (Phase 4a) ------------------------------------------------


def _store(app):
    from tests.fakes import FakeConversationStore

    app.state.container.store = FakeConversationStore()
    return app.state.container.store


def test_a_question_starts_a_conversation_and_both_turns_are_stored(app):
    store = _store(app)
    wire(app, StubRuntime([
        {"type": "text", "text": "Two match."},
        {"type": "projects", "projects": [{"id": "AK-1", "name": "Duo"}]},
        {"type": "done"},
    ]))
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "townhomes in Brampton?"},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    cid = sse(r.text)[0]["conversation_id"]
    assert cid is not None                         # the client learns its id from `start`
    rows = store.rows[cid]
    assert [x["role"] for x in rows] == ["user", "assistant"]
    assert rows[1]["message"] == "Two match."


def test_the_ids_from_the_projects_event_reach_sources(app):
    """The compare-by-name fix, end to end. The runtime is never asked for this
    -- it already emits the cards, so persistence observes the stream."""
    store = _store(app)
    wire(app, StubRuntime([
        {"type": "projects", "projects": [
            {"id": "AK-1", "name": "Duo"},
            {"id": None, "name": "No id yet"},     # PROJECT ID unfilled -- unreferenceable
        ]},
        {"type": "text", "text": "One match."},
        {"type": "done"},
    ]))
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "q"},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    cid = sse(r.text)[0]["conversation_id"]
    assert store.rows[cid][1]["sources"] == [{"id": "AK-1", "name": "Duo"}]


def test_a_second_question_continues_the_same_conversation(app):
    store = _store(app)
    runtime = wire(app)
    with TestClient(app) as client:
        first = client.post("/chat", json={"question": "townhomes in Oakville?"},
                            headers={"Authorization": f"Bearer {TOKEN}"})
        cid = sse(first.text)[0]["conversation_id"]
        client.post("/chat", json={"question": "compare the first two", "conversation_id": cid},
                    headers={"Authorization": f"Bearer {TOKEN}"})
    assert len(store.rows[cid]) == 4
    # And the second call was given the stored thread, not an empty one.
    assert runtime.seen["history"][0].content == "townhomes in Oakville?"


def test_server_history_beats_the_body(app):
    """The body is the phone asserting what was said; the store knows. When both
    arrive the server wins."""
    store = _store(app)
    runtime = wire(app)
    with TestClient(app) as client:
        cid = sse(client.post("/chat", json={"question": "real question"},
                              headers={"Authorization": f"Bearer {TOKEN}"}).text)[0]["conversation_id"]
        client.post(
            "/chat",
            json={"question": "next", "conversation_id": cid,
                  "history": [{"role": "user", "content": "INVENTED"}]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert "INVENTED" not in [t.content for t in runtime.seen["history"]]
    assert store.owner[cid] == "sarath"


def test_a_borrowed_conversation_id_does_not_get_written_into(app):
    """AUR-40 on the write path. history() returning empty is not enough -- an
    empty conversation is a real state and it belongs to somebody."""
    store = _store(app)
    wire(app)
    theirs = _run(store.create(user="priya", title="hers"))
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "q", "conversation_id": theirs},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    assert store.rows[theirs] == []                       # hers is untouched


def test_an_id_that_is_not_ours_starts_a_fresh_conversation(app):
    """The regression, server half. Refusing used to mean returning None, so a
    client holding a stale id -- the next realtor to sign in on a shared phone
    -- got no conversation at all, silently, on every question forever. Refuse
    the id, keep the realtor."""
    store = _store(app)
    wire(app)
    theirs = _run(store.create(user="priya", title="hers"))
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "q", "conversation_id": theirs},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    cid = sse(r.text)[0]["conversation_id"]
    assert cid is not None and cid != theirs
    assert store.owner[cid] == "sarath"
    assert store.rows[theirs] == []                       # and hers is still untouched


def test_only_the_last_turns_are_read_back(app):
    """The store is asked for a window, not the whole thread. Without it a
    conversation kept open for a week costs a growing read on every question."""
    store = _store(app)
    wire(app)
    with TestClient(app) as client:
        cid = sse(client.post("/chat", json={"question": "first"},
                              headers={"Authorization": f"Bearer {TOKEN}"}).text)[0]["conversation_id"]
        for i in range(30):
            _run(store.append(conversation_id=cid, role="user", message=f"q{i}"))
        runtime = wire(app)
        client.post("/chat", json={"question": "next", "conversation_id": cid},
                    headers={"Authorization": f"Bearer {TOKEN}"})
    assert len(runtime.seen["history"]) <= 20


def test_a_dead_store_costs_history_not_the_answer(app):
    """Persistence is the feature that degrades. A realtor with a database
    outage must still get answers."""
    store = _store(app)
    store.up = False
    wire(app)
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "q"},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    events = sse(r.text)
    assert r.status_code == 200
    assert events[0]["conversation_id"] is None
    assert {"type": "text", "text": "hi"} in events    # the answer still arrived


def test_a_stopped_stream_still_records_the_partial_answer(app):
    """A realtor who taps Stop, or a phone that loses signal, reopens the thread
    to a half answer rather than a question with nothing under it."""
    store = _store(app)

    class Dies:
        async def stream(self, **kw):
            yield {"type": "text", "text": "Two mat"}
            raise RuntimeError("connection lost")

        async def healthy(self):
            return True

    wire(app, Dies())
    with TestClient(app) as client:
        r = client.post("/chat", json={"question": "q"},
                        headers={"Authorization": f"Bearer {TOKEN}"})
    cid = sse(r.text)[0]["conversation_id"]
    assert store.rows[cid][1]["message"] == "Two mat"


def test_no_store_still_honours_the_body(app):
    """The rollout path: a phone that has not updated sends its own history and
    must keep working."""
    app.state.container.store = None
    runtime = wire(app)
    with TestClient(app) as client:
        client.post("/chat", json={"question": "q",
                                   "history": [{"role": "user", "content": "earlier"}]},
                    headers={"Authorization": f"Bearer {TOKEN}"})
    assert [t.content for t in runtime.seen["history"]] == ["earlier"]


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)
