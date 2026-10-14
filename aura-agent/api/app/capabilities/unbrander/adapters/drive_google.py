"""GoogleWriter over the Drive v3 REST API, with a service account.

google-auth only signs the service account's token request; every call, the
token exchange included, goes through httpx. That keeps the heavy
google-api-python-client out, and with it a second HTTP stack.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

import httpx
from google.auth import crypt, jwt

from ..ports import DriveWriteFailed

DRIVE = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER = "application/vnd.google-apps.folder"
TIMEOUT_S = 60.0
# Broken connections, 429 and 5xx: three tries, 2 s then 5 s apart (AUTONOMY.md).
RETRY_WAITS_S = (2.0, 5.0)
TOKEN_LIFETIME_S = 3600
TOKEN_MARGIN_S = 60  # renewed this long before Google says it expires


class GoogleDriveWriter:
    def __init__(self, service_account_json: str, shared_drive_id: str, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        info = json.loads(service_account_json)
        self._signer = crypt.RSASigner.from_service_account_info(info)
        self._email = info["client_email"]
        self._token_uri = info.get("token_uri", "https://oauth2.googleapis.com/token")
        self._drive_id = shared_drive_id
        self._http = httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport)
        self._sleep = sleep
        self._token = ""
        self._token_expires = 0.0
        self._token_lock = asyncio.Lock()

    async def find_or_create_folder(self, parent_id: str, name: str) -> tuple[str, bool]:
        query = (f"'{_quoted(parent_id)}' in parents and name = '{_quoted(name)}'"
                 f" and mimeType = '{FOLDER}' and trashed = false")
        found = await self._call("GET", DRIVE, params={
            "q": query, "fields": "files(id)", "corpora": "drive", "driveId": self._drive_id,
            "includeItemsFromAllDrives": "true", "supportsAllDrives": "true",
        })
        if files := found.json()["files"]:
            return files[0]["id"], True
        created = await self._call("POST", DRIVE, params={"supportsAllDrives": "true"},
                                   json={"name": name, "mimeType": FOLDER, "parents": [parent_id]})
        return created.json()["id"], False

    async def upload_pdf(self, folder_id: str, name: str, data: bytes) -> str:
        # Resumable, not multipart: Google's multipart upload is for files of 5 MB
        # or less, and a cleaned brochure is often more.
        session = await self._call(
            "POST", UPLOAD, params={"uploadType": "resumable", "supportsAllDrives": "true"},
            json={"name": name, "parents": [folder_id], "mimeType": "application/pdf"},
        )
        uploaded = await self._call("PUT", session.headers["Location"], content=data,
                                    headers={"Content-Type": "application/pdf"})
        return uploaded.json()["id"]

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                    **request) -> httpx.Response:
        for attempt, wait in enumerate((*RETRY_WAITS_S, None), start=1):
            try:
                signed = {**(headers or {}),
                          "Authorization": f"Bearer {await self._access_token()}"}
                response = await self._http.request(method, url, headers=signed, **request)
            except httpx.TransportError as error:
                problem = f"{type(error).__name__}: {error}"
            else:
                if response.is_success:
                    return response
                problem = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code == 401:
                    self._token = ""  # revoked or expired early: fetch a new one and retry
                elif response.status_code != 429 and response.status_code < 500:
                    raise DriveWriteFailed(f"Drive {method} refused: {problem}")
            if wait is None:
                raise DriveWriteFailed(f"Drive {method} failed {attempt} times: {problem}")
            await self._sleep(wait)
        raise AssertionError("unreachable")

    async def _access_token(self) -> str:
        async with self._token_lock:
            if self._token and time.time() < self._token_expires - TOKEN_MARGIN_S:
                return self._token
            now = int(time.time())
            assertion = jwt.encode(self._signer, {
                "iss": self._email, "scope": SCOPE, "aud": self._token_uri,
                "iat": now, "exp": now + TOKEN_LIFETIME_S,
            })
            response = await self._http.post(self._token_uri, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion.decode(),
            })
            if not response.is_success:
                raise DriveWriteFailed(
                    f"service account sign-in refused: HTTP {response.status_code}")
            granted = response.json()
            self._token = granted["access_token"]
            self._token_expires = now + granted.get("expires_in", TOKEN_LIFETIME_S)
            return self._token


def _quoted(value: str) -> str:
    """A value inside single quotes in a Drive query: backslash and quote escaped,
    so a project called "Builder's Row" finds its folder instead of failing."""
    return value.replace("\\", "\\\\").replace("'", "\\'")
