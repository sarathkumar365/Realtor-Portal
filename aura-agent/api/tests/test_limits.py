"""AUR-21: a single account cannot flood the model server."""

import pytest
from fastapi.testclient import TestClient

from app.container import Container
from app.domain import Claims, Role
from app.limits import Window, client_ip
from app.main import create_app
from tests.conftest import StubPortal
from tests.fakes import FakeAuthVerifier, FakeProjectRepo, make_token
from tests.test_chat_endpoint import StubRuntime

TOKEN = make_token("sarath")


def test_a_window_allows_up_to_its_limit_then_refuses():
    w = Window(limit=3, seconds=60)
    assert [w.check("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert w.check("a") > 0


def test_a_window_counts_each_key_separately():
    """Otherwise the busiest realtor rate-limits the whole brokerage."""
    w = Window(limit=1, seconds=60)
    assert w.check("sarath") == 0.0
    assert w.check("priya") == 0.0
    assert w.check("sarath") > 0


def test_refused_attempts_do_not_extend_the_window():
    """Hammering must not push the window forward into a permanent ban."""
    w = Window(limit=1, seconds=60)
    w.check("a")
    for _ in range(5):
        w.check("a")
    assert len(w._hits["a"]) == 1


def test_the_window_forgets_old_hits():
    w = Window(limit=2, seconds=0.01)
    w.check("a")
    w.check("a")
    assert w.check("a") > 0
    import time as _t

    _t.sleep(0.02)
    assert w.check("a") == 0.0


class _Req:
    def __init__(self, xff=None, peer="10.0.0.1"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": peer})()


def test_the_address_our_own_proxy_wrote_is_the_one_used():
    """The LAST entry, not the first. This used to assert the opposite, and it
    was wrong: keying on the first entry handed the counter to the caller."""
    assert client_ip(_Req("9.9.9.9, 203.0.113.7")) == "203.0.113.7"


def test_a_single_entry_is_still_the_client():
    assert client_ip(_Req("203.0.113.7")) == "203.0.113.7"


def test_with_no_proxy_header_the_peer_is_the_client():
    assert client_ip(_Req(peer="198.51.100.4")) == "198.51.100.4"


def test_a_spoofed_prefix_cannot_reset_the_counter(tight):
    """A fresh X-Forwarded-For per request used to buy a fresh allowance.

    Written the way the edge writes it: what the caller sent, then the real peer.
    The caller varies its half; the ceiling must hold on ours.
    """
    body = {"user": "sarath", "password": "x"}
    with TestClient(tight) as client:
        codes = [
            client.post(
                "/login", json=body, headers={"X-Forwarded-For": f"9.9.9.{i}, 203.0.113.7"}
            ).status_code
            for i in range(6)
        ]
    assert 429 in codes
    assert codes[-1] == 429


def test_the_counter_map_is_actually_bounded():
    """_prune only dropped expired entries, so a burst of live callers grew the
    dict without limit."""
    from app.limits import MAX_KEYS

    w = Window(limit=20, seconds=3600)
    for i in range(MAX_KEYS + 5_000):
        w.check(f"ip-{i}")
    assert len(w._hits) <= MAX_KEYS


def test_eviction_forgives_rather_than_refuses():
    """Eviction must forgive a request, never refuse one."""
    w = Window(limit=1, seconds=3600)
    w.check("victim")
    assert w.check("victim") > 0
    w._hits.clear()                      # what eviction does, in the worst case
    assert w.check("victim") == 0.0


@pytest.fixture
def tight(settings):
    """An app whose ceilings are small enough to reach in a test."""
    cfg = settings.model_copy(update={"chat_per_hour": 2, "login_per_hour": 2, "doctor_per_hour": 2})
    application = create_app(cfg)
    application.state.container = Container(
        settings=cfg, portal=StubPortal(), auth=FakeAuthVerifier()
    )
    application.state.container.runtime = StubRuntime()
    application.state.container.projects = FakeProjectRepo([])
    return application


def _ask(client):
    return client.post(
        "/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"}
    )


def test_chat_refuses_past_the_ceiling(tight):
    with TestClient(tight) as client:
        assert [_ask(client).status_code for _ in range(3)] == [200, 200, 429]


def test_a_refused_chat_says_when_to_come_back(tight):
    with TestClient(tight) as client:
        _ask(client), _ask(client)
        r = _ask(client)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_the_ceiling_is_per_user_not_per_service(tight):
    """One realtor in a retry loop must not lock the other nineteen out.

    The identity is swapped on the verifier, not by sending a second token:
    FakeAuthVerifier answers the same claims for any token.
    """
    with TestClient(tight) as client:
        _ask(client), _ask(client)
        assert _ask(client).status_code == 429
        tight.state.container.auth.claims = Claims(
            user="priya", role=Role.REALTOR, issued_ms=0
        )
        r = _ask(client)
    assert r.status_code == 200


def test_login_is_limited_by_address(tight):
    """Unauthenticated, and it proxies passwords to the portal's own lockout."""
    body = {"user": "sarath", "password": "x"}
    with TestClient(tight) as client:
        codes = [client.post("/login", json=body).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_doctor_is_limited_by_address(tight):
    """?fresh=1 costs a portal call, and unverified callers still get a reply."""
    h = {"Authorization": "Bearer whatever"}
    with TestClient(tight) as client:
        codes = [client.get("/doctor", headers=h).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_an_app_with_no_limits_attached_is_unlimited(app):
    """An app that never called create_app is unlimited, not broken."""
    del app.state.limits
    app.state.container.runtime = StubRuntime()
    app.state.container.projects = FakeProjectRepo([])
    with TestClient(app) as client:
        assert all(_ask(client).status_code == 200 for _ in range(5))
