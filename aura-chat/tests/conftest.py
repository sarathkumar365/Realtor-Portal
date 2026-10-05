import pytest

from app.config import Settings
from app.container import Container
from app.main import create_app
from tests.fakes import TEST_SECRET, FakeAuthVerifier


class StubPortal:
    def __init__(self, healthy: bool = True) -> None:
        self._healthy = healthy
        self.calls: list[tuple[str, dict]] = []

    async def call(self, action: str, *, auth: str | None = None, **params):
        self.calls.append((action, params))
        return {"ok": True, "user": "sarath", "role": "realtor"}

    async def healthy(self) -> bool:
        return self._healthy

    async def aclose(self) -> None:
        return None


@pytest.fixture
def settings() -> Settings:
    return Settings(
        token_secret=TEST_SECRET,
        exec_url="https://example.invalid/exec",
        _env_file=None,
    )


@pytest.fixture
def app(settings):
    # Explicit settings, so a developer's .env cannot change what a test asserts.
    application = create_app(settings)
    application.dependency_overrides = {}
    application.state.container = Container(
        settings=settings,
        portal=StubPortal(),
        auth=FakeAuthVerifier(),
    )
    return application
