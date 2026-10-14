"""The Drive adapter against an httpx mock transport: no network, no Google."""

import json
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.capabilities.unbrander.adapters.drive_google import GoogleDriveWriter
from app.capabilities.unbrander.ports import DriveWriteFailed

TOKEN_URI = "https://oauth2.example.invalid/token"


@pytest.fixture(scope="module")
def key_json() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return json.dumps({"type": "service_account", "client_email": "unbrander@test.invalid",
                       "private_key": pem, "private_key_id": "k1", "token_uri": TOKEN_URI})


class Google:
    """Answers in order from `replies` for Drive calls; always grants tokens."""

    def __init__(self, *replies: httpx.Response) -> None:
        self.replies = list(replies)
        self.calls: list[httpx.Request] = []
        self.tokens = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URI:
            self.tokens += 1
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
            return httpx.Response(200, json={"access_token": f"token{self.tokens}",
                                             "expires_in": 3600})
        self.calls.append(request)
        return self.replies.pop(0)


def writer(key_json: str, google: Google, waits: list[float] | None = None) -> GoogleDriveWriter:
    async def sleep(seconds: float) -> None:
        if waits is not None:
            waits.append(seconds)
    return GoogleDriveWriter(key_json, "drive1", transport=httpx.MockTransport(google),
                             sleep=sleep)


async def test_an_existing_folder_is_found_inside_the_shared_drive(key_json):
    google = Google(httpx.Response(200, json={"files": [{"id": "f9"}]}))
    assert await writer(key_json, google).find_or_create_folder("root", "Builder's Row") == (
        "f9", True)
    params = google.calls[0].url.params
    assert params["q"] == ("'root' in parents and name = 'Builder\\'s Row' and mimeType ="
                           " 'application/vnd.google-apps.folder' and trashed = false")
    assert (params["driveId"], params["corpora"], params["supportsAllDrives"]) == (
        "drive1", "drive", "true")
    assert google.calls[0].headers["Authorization"] == "Bearer token1"


async def test_a_missing_folder_is_created_under_its_parent(key_json):
    google = Google(httpx.Response(200, json={"files": []}),
                    httpx.Response(200, json={"id": "new"}))
    assert await writer(key_json, google).find_or_create_folder("root", "Vaughan") == (
        "new", False)
    assert json.loads(google.calls[1].content) == {
        "name": "Vaughan", "mimeType": "application/vnd.google-apps.folder", "parents": ["root"]}


async def test_a_pdf_is_uploaded_in_a_resumable_session(key_json):
    google = Google(httpx.Response(200, headers={"Location": "https://upload.invalid/s1"}),
                    httpx.Response(200, json={"id": "pdf1"}))
    assert await writer(key_json, google).upload_pdf("folder", "plans.pdf", b"%PDF-1") == "pdf1"
    start, body = google.calls
    assert start.url.params["uploadType"] == "resumable"
    assert json.loads(start.content)["parents"] == ["folder"]
    assert (str(body.url), body.content) == ("https://upload.invalid/s1", b"%PDF-1")


async def test_one_token_serves_many_calls(key_json):
    google = Google(httpx.Response(200, json={"files": [{"id": "a"}]}),
                    httpx.Response(200, json={"files": [{"id": "b"}]}))
    drive = writer(key_json, google)
    await drive.find_or_create_folder("root", "Ontario")
    await drive.find_or_create_folder("root", "Vaughan")
    assert google.tokens == 1


async def test_a_busy_drive_is_retried_two_then_five_seconds_apart(key_json):
    waits: list[float] = []
    google = Google(httpx.Response(503), httpx.Response(429),
                    httpx.Response(200, json={"files": [{"id": "f"}]}))
    assert (await writer(key_json, google, waits).find_or_create_folder("r", "x"))[0] == "f"
    assert waits == [2.0, 5.0]


async def test_a_drive_still_busy_after_three_tries_fails_the_write(key_json):
    google = Google(httpx.Response(503), httpx.Response(503), httpx.Response(503))
    with pytest.raises(DriveWriteFailed, match="failed 3 times: HTTP 503"):
        await writer(key_json, google, []).find_or_create_folder("r", "x")


async def test_a_refusal_fails_at_once_without_retrying(key_json):
    waits: list[float] = []
    google = Google(httpx.Response(403, text="insufficient permissions"))
    with pytest.raises(DriveWriteFailed, match="refused: HTTP 403"):
        await writer(key_json, google, waits).find_or_create_folder("r", "x")
    assert waits == [] and len(google.calls) == 1


async def test_an_expired_token_is_replaced_and_the_call_repeated(key_json):
    google = Google(httpx.Response(401), httpx.Response(200, json={"files": [{"id": "f"}]}))
    assert (await writer(key_json, google, []).find_or_create_folder("r", "x"))[0] == "f"
    assert google.tokens == 2
    assert google.calls[1].headers["Authorization"] == "Bearer token2"
