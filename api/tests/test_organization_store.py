"""The editable organization profile: GET/PUT /admin/organization and boot loading."""

import pytest
from fastapi.testclient import TestClient

from app import container as container_mod
from app.config import Settings
from app.domain import Brand, Claims, MarkWord, Organization, Role
from tests.fakes import FakeAgentRuntime, FakeAuthVerifier, FakeOrganizationStore

AUTH = {"Authorization": "Bearer token"}
NORTH_STAR = Organization(name="North Star Homes", short_name="North Star",
                          assistant_name="Polaris", region="Ottawa",
                          brand=Brand(mark_words=(MarkWord(text="NORTH", colour="#112233"),),
                                      font="Courier"))


@pytest.fixture
def admin(app):
    services = app.state.container
    services.auth = FakeAuthVerifier(Claims(user="sudhanshu", role=Role.ADMIN, issued_ms=0))
    services.organization_store = FakeOrganizationStore()
    services.runtime_for = lambda organization: FakeAgentRuntime(
        [{"type": "done", "organization": organization.name}])
    return services


def test_the_defaults_are_served_until_a_profile_is_saved(app, admin):
    with TestClient(app) as client:
        assert client.get("/admin/organization", headers=AUTH).json()["name"] == "Aura Key Realty"


def test_a_saved_profile_is_stored_and_used_by_chat_at_once(app, admin):
    with TestClient(app) as client:
        response = client.put("/admin/organization", headers=AUTH,
                              json=NORTH_STAR.model_dump(mode="json"))
        assert response.status_code == 200
        assert client.get("/admin/organization", headers=AUTH).json()["name"] == "North Star Homes"
    assert admin.organization_store.saved == NORTH_STAR
    assert admin.organization_store.saved_by == "sudhanshu"
    assert admin.organization == NORTH_STAR
    assert admin.runtime.chunks == [{"type": "done", "organization": "North Star Homes"}]


def test_a_realtor_can_neither_read_nor_change_the_profile(app, admin):
    admin.auth = FakeAuthVerifier()
    with TestClient(app) as client:
        assert client.get("/admin/organization", headers=AUTH).status_code == 403
        assert client.put("/admin/organization", headers=AUTH,
                          json=NORTH_STAR.model_dump(mode="json")).status_code == 403
    assert admin.organization_store.saved is None


@pytest.mark.parametrize("change", [
    {"brand": {"mark_words": [{"text": "NORTH", "colour": "navy"}]}},
    {"brand": {"font": "Comic Sans"}},
    {"brand": {"mark_words": [{"text": "NORTH-STAR", "colour": "#112233"}]}},
])
def test_an_invalid_profile_is_refused(app, admin, change):
    body = {**NORTH_STAR.model_dump(mode="json"), **change}
    with TestClient(app) as client:
        assert client.put("/admin/organization", headers=AUTH, json=body).status_code == 422
    assert admin.organization_store.saved is None


def test_without_a_database_the_profile_cannot_be_saved(app, admin):
    admin.organization_store = None
    with TestClient(app) as client:
        assert client.put("/admin/organization", headers=AUTH,
                          json=NORTH_STAR.model_dump(mode="json")).status_code == 503


def test_boot_loads_the_saved_profile(app, admin):
    admin.organization_store = FakeOrganizationStore(saved=NORTH_STAR)
    with TestClient(app):
        assert admin.organization == NORTH_STAR
        assert admin.runtime.chunks[0]["organization"] == "North Star Homes"


def test_switching_the_worker_on_without_its_settings_fails_at_build():
    settings = Settings(token_secret="x", exec_url="https://e.invalid", unbrander_enabled=True,
                        _env_file=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL, OPENROUTER_API_KEY"):
        container_mod.build(settings)


def test_the_worker_runs_without_drive_and_filing_is_then_unavailable():
    settings = Settings(token_secret="x", exec_url="https://e.invalid", unbrander_enabled=True,
                        database_url="postgresql://localhost/none", openrouter_api_key="k",
                        _env_file=None)
    services = container_mod.build(settings)
    assert services.worker is not None and services.drive is None


def test_a_drive_key_without_its_folder_ids_fails_at_build():
    settings = Settings(token_secret="x", exec_url="https://e.invalid",
                        google_service_account_json="{}", _env_file=None)
    with pytest.raises(RuntimeError, match="DRIVE_SHARED_DRIVE_ID, DRIVE_ROOT_FOLDER_ID"):
        container_mod.build(settings)


def test_the_worker_is_not_built_while_switched_off():
    settings = Settings(token_secret="x", exec_url="https://e.invalid", _env_file=None)
    services = container_mod.build(settings)
    assert services.worker is None and services.jobs is None


async def test_boot_refuses_to_run_the_worker_without_ocr(app):
    services = app.state.container
    services.worker = object()
    services.ocr_problem = lambda: "tesseract language data not found"
    with pytest.raises(RuntimeError, match="OCR cannot run"):
        await services.start()


def test_a_database_down_at_boot_serves_the_defaults_instead_of_stopping(app, admin):
    admin.organization_store.up = False
    with TestClient(app) as client:
        assert client.get("/admin/organization", headers=AUTH).json()["name"] == "Aura Key Realty"
