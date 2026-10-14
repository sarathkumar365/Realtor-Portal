"""HTTP client for the Apps Script web app -- Aura Chat's data plane.

Every call is a POST with a text/plain body, exactly as the PWA does it:
that is a CORS "simple request" (Apps Script cannot answer a preflight), and
it keeps the session token out of query strings, where it would land in the
execution log, browser history and the Referer of any outbound link.

Apps Script answers a POST with a 302 to script.googleusercontent.com and
serves the JSON from there, so redirects must be followed.
"""

import json
import time
from typing import Any

import httpx


class PortalError(RuntimeError):
    """The portal did not answer with JSON we can use."""


class PortalClient:
    # How long a health verdict is reused. /health is public and gets polled by
    # the platform and by any uptime monitor; without this, a 30-second probe
    # is ~2,900 Apps Script executions a day out of a daily budget the portal
    # itself has to share. A failure is held far more briefly so a recovery
    # shows up quickly rather than being masked for a minute.
    HEALTH_TTL_OK_S = 60.0
    HEALTH_TTL_FAIL_S = 5.0

    def __init__(self, exec_url: str, *, timeout_s: float = 30.0) -> None:
        self._url = exec_url
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None
        self._health: tuple[float, bool] | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={"Content-Type": "text/plain;charset=utf-8"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(
        self, action: str, *, auth: str | None = None, timeout_s: float | None = None, **params: Any
    ) -> dict:
        """Invoke one action on the portal's dispatcher.

        `auth` is the *caller's own* token, forwarded unchanged. This service
        holds no service account and has no standing privilege: whatever the
        portal will not show that realtor, it will not show Aura Chat either.

        `timeout_s` overrides the default for one call. A cache-busting rebuild
        walks every city tab and takes about a minute, which the budget sized for
        an ordinary read would cut off.
        """
        if not self._url:
            raise PortalError("EXEC_URL is not configured")
        body: dict[str, Any] = {"action": action, **params}
        if auth:
            body["auth"] = auth
        http = await self._http()
        try:
            res = await http.post(
                self._url,
                content=json.dumps(body),
                timeout=timeout_s if timeout_s is not None else self._timeout,
            )
        except httpx.HTTPError as exc:
            raise PortalError(f"portal unreachable: {exc}") from exc
        if res.status_code != 200:
            raise PortalError(f"portal HTTP {res.status_code}")
        # A deployment that has been re-scoped serves Google's sign-in HTML with
        # a 200. Treating that as data would poison every downstream reader, so
        # anything that is not JSON is an error, not a payload.
        try:
            data = res.json()
        except ValueError as exc:
            raise PortalError("portal did not return JSON (deployment re-scoped?)") from exc
        if not isinstance(data, dict):
            raise PortalError("portal returned a non-object payload")
        return data

    async def healthy(self) -> bool:
        """Unauthenticated probe. 'login required' is the healthy answer: it
        proves the deployment is live and the gate is closed.

        Cached: this is a real request against the portal, and the whole reason
        Aura Chat runs outside Apps Script is to stop its traffic competing with
        the realtors' own.
        """
        now = time.monotonic()
        if self._health is not None:
            at, ok = self._health
            if now - at < (self.HEALTH_TTL_OK_S if ok else self.HEALTH_TTL_FAIL_S):
                return ok
        try:
            data = await self.call("cities")
            ok = data.get("ok") is False or "cities" in data
        except PortalError:
            ok = False
        self._health = (now, ok)
        return ok
