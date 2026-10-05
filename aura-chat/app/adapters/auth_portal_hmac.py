"""Verifier for the portal's session token.

Mirrors makeToken_/checkToken_ in the Apps Script project:

    raw   = user | role | credGen | issuedAtMillis
    token = base64url(raw) . base64url(HMAC-SHA256(raw, TOKEN_SECRET))

Two things this cannot check on its own, both requiring the LOGIN sheet: the
credential fingerprint (credGen) and whether the account still exists. So the
signature and window are checked locally, and liveness is delegated to the
portal's own `session` action -- the one place that can see the sheet.
"""

import base64
import hashlib
import hmac
import time

from app.domain import Claims, Role

from .portal_client import PortalClient, PortalError


def _b64url_decode(s: str) -> bytes:
    # Apps Script emits padded output, but a token that has been through a
    # careless copy may arrive without it.
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


class PortalHmacAuthVerifier:
    def __init__(
        self,
        secret: str,
        portal: PortalClient,
        *,
        session_ms: int,
        liveness_ttl_s: float = 60.0,
        max_cached: int = 2000,
    ) -> None:
        self._secret = secret.encode()
        self._portal = portal
        self._session_ms = session_ms
        self._ttl = liveness_ttl_s
        self._max = max_cached
        self._seen: dict[str, tuple[float, Claims]] = {}

    def _prune(self, now: float) -> None:
        """Drop what the TTL has already invalidated, and cap what is left.

        Sessions slide -- the portal mints a fresh token on every app launch --
        so one realtor produces a stream of distinct token strings over a day.
        Without this the dict only ever grows, and a process that stays up for
        a week ends up holding every token it has ever been shown.
        """
        for tok in [t for t, (at, _) in self._seen.items() if now - at >= self._ttl]:
            del self._seen[tok]
        if len(self._seen) >= self._max:
            # Everything is still live but there are too many of them; evict
            # oldest-first. A wrongly evicted entry costs one portal call, not
            # a session, so this is always safe to do.
            for tok, _ in sorted(self._seen.items(), key=lambda kv: kv[1][0])[: self._max // 2]:
                del self._seen[tok]

    def verify_local(self, token: str) -> Claims | None:
        """Signature and window only. No network."""
        if not self._secret or not token:
            return None
        parts = token.split(".")
        if len(parts) != 2:
            return None
        try:
            raw = _b64url_decode(parts[0]).decode("utf-8")
        except Exception:
            return None
        want = _b64url(hmac.new(self._secret, raw.encode("utf-8"), hashlib.sha256).digest())
        # Constant time: a byte-wise comparison here would leak the signature
        # one character at a time to anyone willing to measure.
        if not hmac.compare_digest(want, parts[1]):
            return None
        # Parsed from the END. The username is the one field that may itself
        # contain a '|', so counting from the front misreads every other field.
        bits = raw.split("|")
        if len(bits) < 4:
            return None
        try:
            issued = int(bits[-1])
        except ValueError:
            return None
        role_raw = bits[-3]
        user = "|".join(bits[: len(bits) - 3])
        if not user or not issued:
            return None
        if (time.time() * 1000) - issued > self._session_ms:
            return None
        try:
            role = Role(role_raw)
        except ValueError:
            return None
        return Claims(user=user, role=role, issued_ms=issued)

    async def verify(self, token: str) -> Claims | None:
        """Local checks, then the portal's ruling on whether the account lives.

        The portal read is cached briefly: without it every message in a
        conversation would cost a sheet round trip, and the portal's own
        liveness cache is 5 minutes anyway, so a shorter TTL here buys nothing.
        """
        claims = self.verify_local(token)
        if claims is None:
            return None
        hit = self._seen.get(token)
        now = time.monotonic()
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        try:
            data = await self._portal.call("session", auth=token)
        except PortalError:
            # The portal being unwell is not the same as the token being bad.
            # Refusing here would sign the whole team out over an outage, so a
            # locally valid token is honoured and the liveness check retried on
            # the next message.
            return claims
        if not data.get("ok"):
            self._seen.pop(token, None)
            return None
        self._prune(now)
        self._seen[token] = (now, claims)
        return claims
