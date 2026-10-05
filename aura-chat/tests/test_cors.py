"""The browser's half of the contract.

The PWA lives on another origin, so every one of these is the difference
between a working chat screen and a console full of blocked requests -- and,
in the negative cases, between an allowlist and an open door.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ALLOWED = "https://aurakey.netlify.app"
PREVIEW = "https://deploy-preview-7--aurakey.netlify.app"


def _client(**overrides) -> TestClient:
    cfg = Settings(token_secret="x" * 32, exec_url="https://e.invalid", _env_file=None, **overrides)
    return TestClient(create_app(cfg))


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_named_origin_is_allowed():
    r = _preflight(_client(allowed_origins=ALLOWED), ALLOWED)
    assert r.headers.get("access-control-allow-origin") == ALLOWED


def test_unnamed_origin_is_not():
    """The whole point. An origin nobody listed gets no header, so the browser
    refuses the request -- a page a realtor stumbles onto cannot spend the
    token their PWA is holding."""
    r = _preflight(_client(allowed_origins=ALLOWED), "https://evil.example")
    assert r.headers.get("access-control-allow-origin") is None


def test_authorization_header_is_permitted():
    """EventSource was rejected partly because it cannot send this header. If
    the preflight does not allow it, fetch cannot either, and we are back to
    putting the token in the URL."""
    r = _preflight(_client(allowed_origins=ALLOWED), ALLOWED)
    assert "authorization" in r.headers.get("access-control-allow-headers", "").lower()


def test_credentials_are_never_allowed():
    """Off by design: the token is a bearer header, not a cookie. With it off,
    a wrong entry in the list cannot hand a third party a live session."""
    r = _preflight(_client(allowed_origins=ALLOWED), ALLOWED)
    assert r.headers.get("access-control-allow-credentials") is None


def test_default_is_local_only_and_never_a_wildcard():
    cfg = Settings(token_secret="x" * 32, exec_url="https://e.invalid", _env_file=None)
    assert "*" not in cfg.allowed_origins
    assert all(o.startswith("http://localhost:") for o in cfg.origins)
    assert cfg.allowed_origin_regex == ""


def test_preview_regex_is_off_until_someone_sets_it():
    """Netlify's draft deploys get a random subdomain, so previews can only be
    reached by regex -- which is a standing hole, and must not be open by
    default."""
    assert _preflight(_client(allowed_origins=ALLOWED), PREVIEW).headers.get(
        "access-control-allow-origin"
    ) is None
    opened = _client(
        allowed_origins=ALLOWED,
        allowed_origin_regex=r"https://[a-z0-9-]+--aurakey\.netlify\.app",
    )
    assert _preflight(opened, PREVIEW).headers.get("access-control-allow-origin") == PREVIEW


def test_origins_property_drops_blanks():
    cfg = Settings(
        token_secret="x" * 32,
        exec_url="https://e.invalid",
        _env_file=None,
        allowed_origins=f"{ALLOWED}, ,",
    )
    assert cfg.origins == [ALLOWED]


def test_the_headers_a_browser_must_read_are_exposed(app):
    """Cross-origin JS sees only the CORS safelist unless a header is named
    here. Retry-After is not on that safelist: without it the PWA's 429 branch
    read null every time and told a realtor refused for the next hour to "try
    again in a moment". X-Request-Id is the id they quote when reporting a
    failure, and it is useless if the page cannot read it.
    """
    # A real response, not a preflight: access-control-expose-headers only
    # appears on the actual request. The app fixture supplies a container, so
    # this does not build real adapters off whatever .env happens to say.
    with TestClient(app) as client:
        r = client.get("/health", headers={"Origin": "http://localhost:4600"})
    exposed = {
        h.strip().lower()
        for h in r.headers.get("access-control-expose-headers", "").split(",")
    }
    assert {"retry-after", "x-request-id"} <= exposed
