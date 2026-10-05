from fastapi.testclient import TestClient

from tests.fakes import make_token


def test_health_is_public_and_terse(app):
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body == {"status": "ok", "ok": True}


def test_health_leaks_nothing_about_configuration(app, settings):
    """A public endpoint must not tell a stranger which secret is missing --
    that is a hint about when forging a token might work."""
    app.state.container.settings = settings.model_copy(update={"token_secret": ""})
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "down"
    assert "TOKEN_SECRET" not in str(body)
    assert "checks" not in body


def test_doctor_requires_a_token(app):
    with TestClient(app) as client:
        assert client.get("/doctor").status_code == 401


def test_doctor_names_the_missing_setting(app, settings):
    """The same fact /health withholds, /doctor states plainly -- the caller
    has proved who they are."""
    app.state.container.settings = settings.model_copy(update={"token_secret": ""})
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    assert body["status"] == "down"
    assert "TOKEN_SECRET" in body["checks"]["config"]["detail"]


def test_doctor_checks_the_data_path_not_just_reachability(app):
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    # portal_auth proves TOKEN_SECRET matches; project_data proves Aura can
    # actually read projects. Reachability alone proves neither.
    assert body["checks"]["portal_auth"]["ok"] is True
    assert body["checks"]["project_data"]["ok"] is None  # repo lands in Phase 2
    assert body["checks"]["portal_reachable"]["ms"] >= 0


def test_a_failing_optional_check_degrades_rather_than_downs(app):
    """Losing history is an annoyance; losing project data is an outage."""
    class BrokenStore:
        async def healthy(self):
            return False

    app.state.container.store = BrokenStore()
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    assert body["status"] == "degraded"
    assert body["ok"] is False


def test_a_dependency_that_raises_does_not_500_the_doctor(app):
    class ExplodingStore:
        async def healthy(self):
            raise RuntimeError("connection refused")

    app.state.container.store = ExplodingStore()
    with TestClient(app) as client:
        r = client.get("/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"})
    assert r.status_code == 200
    assert "connection refused" in r.json()["checks"]["conversation_store"]["detail"]


def test_me_requires_a_token(app):
    with TestClient(app) as client:
        assert client.get("/me").status_code == 401


def test_me_rejects_a_non_bearer_header(app):
    with TestClient(app) as client:
        r = client.get("/me", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_me_returns_the_verified_identity(app):
    with TestClient(app) as client:
        r = client.get("/me", headers={"Authorization": f"Bearer {make_token('sarath')}"})
    assert r.status_code == 200
    assert r.json()["user"] == "sarath"


def test_me_401s_when_the_verifier_refuses(app):
    app.state.container.auth.allow = False
    with TestClient(app) as client:
        r = client.get("/me", headers={"Authorization": f"Bearer {make_token('sarath')}"})
    assert r.status_code == 401


async def test_portal_health_probe_is_cached():
    """/health is public and gets polled; each uncached probe is an Apps Script
    execution out of the budget the portal itself has to share."""
    from tests.conftest import StubPortal

    from app.adapters.portal_client import PortalClient

    class CountingClient(PortalClient):
        def __init__(self):
            super().__init__("https://example.invalid/exec")
            self.calls = 0

        async def call(self, action, *, auth=None, **params):
            self.calls += 1
            return {"ok": False, "error": "login required"}

    c = CountingClient()
    assert await c.healthy() is True
    assert await c.healthy() is True
    assert await c.healthy() is True
    assert c.calls == 1
    _ = StubPortal  # imported for parity with the other tests in this module


def test_doctor_still_answers_when_nothing_verifies(app):
    """A doctor that stops working when the patient is sick is no use.

    A wrong TOKEN_SECRET means no token verifies -- which is precisely when
    somebody needs the diagnosis.
    """
    app.state.container.auth.allow = False
    with TestClient(app) as client:
        r = client.get("/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"})
    assert r.status_code == 200
    assert r.json()["checks"]["token_verification"]["ok"] is False
    assert r.json()["user"] is None


def test_doctor_distinguishes_a_wrong_key_from_a_stale_token(app):
    """The two failures look identical from the outside: every realtor gets a
    401 while /health stays green. The portal's verdict tells them apart."""
    app.state.container.auth.allow = False  # nothing verifies here...
    with TestClient(app) as client:  # ...but StubPortal accepts the token
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    assert "TOKEN_SECRET does not match" in body["checks"]["token_verification"]["detail"]


def test_doctor_redacts_other_detail_from_an_unverified_caller(app, settings):
    app.state.container.auth.allow = False
    app.state.container.settings = settings.model_copy(update={"token_secret": ""})
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    assert body["checks"]["config"].get("detail", "") == ""
    assert body["checks"]["token_verification"]["detail"]


def test_doctor_still_requires_some_token(app):
    with TestClient(app) as client:
        assert client.get("/doctor").status_code == 401


def test_doctor_reports_unreadable_prices(app):
    """A price the parser cannot read is a project that silently drops out of
    every price filter -- it should surface as a number, not as a thin answer."""
    class Repo:
        total_rows, unparsed_prices = 40, 3

        async def search(self, f, *, auth):
            return []

        async def refresh(self, *, auth):
            return 0

    app.state.container.projects = Repo()
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    q = body["checks"]["data_quality"]
    assert q["ok"] is False and "3 with a price" in q["detail"]
    assert q["critical"] is False


def test_doctor_reports_future_dated_projects(app):
    """A date after today is a typo recent() now excludes. Dropping it silently
    would trade a wrong answer for a missing one; /doctor names the count."""

    class Repo:
        total_rows, unparsed_prices, future_dated = 161, 0, 1

        async def search(self, f, *, auth):
            return []

        async def refresh(self, *, auth):
            return 0

    app.state.container.projects = Repo()
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    q = body["checks"]["data_quality"]
    assert q["ok"] is False and "1 dated in the future" in q["detail"]
    assert q["critical"] is False


def test_unreadable_prices_degrade_rather_than_down(app):
    class Repo:
        total_rows, unparsed_prices = 40, 3

        async def search(self, f, *, auth):
            from app.domain import Project, SearchPage

            return SearchPage(items=[Project(name="X", city="Y")], total=1)

        async def refresh(self, *, auth):
            return 1

    app.state.container.projects = Repo()
    with TestClient(app) as client:
        body = client.get(
            "/doctor", headers={"Authorization": f"Bearer {make_token('sarath')}"}
        ).json()
    assert body["status"] == "degraded"


class LoginPortal:
    """A portal that accepts one password and refuses everything else."""

    def __init__(self, ok=True, error="invalid id or password"):
        self.ok, self.error, self.calls = ok, error, []

    async def call(self, action, *, auth=None, **params):
        self.calls.append((action, params))
        if action == "login" and self.ok:
            return {"ok": True, "token": "tok.sig", "name": "Sarath", "role": "realtor"}
        return {"ok": False, "error": self.error}

    async def healthy(self):
        return True

    async def aclose(self):
        return None


def test_login_returns_a_token(app):
    app.state.container.portal = LoginPortal()
    with TestClient(app) as client:
        r = client.post("/login", json={"user": "sarath", "password": "hunter2"})
    assert r.status_code == 200 and r.json()["token"] == "tok.sig"


def test_login_passes_the_portals_own_wording_through(app):
    """'too many attempts' and 'invalid id or password' mean different things
    to whoever is trying to sign in."""
    app.state.container.portal = LoginPortal(ok=False, error="too many attempts — try again in a few minutes")
    with TestClient(app) as client:
        r = client.post("/login", json={"user": "sarath", "password": "no"})
    assert r.status_code == 401 and "too many attempts" in r.json()["detail"]


def test_login_never_echoes_the_password(app):
    portal = LoginPortal()
    app.state.container.portal = portal
    with TestClient(app) as client:
        r = client.post("/login", json={"user": "sarath", "password": "hunter2"})
    assert "hunter2" not in r.text
    # It goes to the portal once and is not retained anywhere here.
    assert portal.calls[0][0] == "login"


def test_login_requires_both_fields(app):
    app.state.container.portal = LoginPortal()
    with TestClient(app) as client:
        assert client.post("/login", json={"user": "sarath"}).status_code == 422
        assert client.post("/login", json={"user": "", "password": "x"}).status_code == 422
