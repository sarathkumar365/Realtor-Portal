"""The token contract with Apps Script. If these fail, realtors cannot sign in."""

import time

import pytest

from app.adapters.auth_portal_hmac import PortalHmacAuthVerifier
from app.domain import Role
from tests.conftest import StubPortal
from tests.fakes import TEST_SECRET, make_token

SESSION_MS = 7 * 24 * 60 * 60 * 1000


def verifier(secret: str = TEST_SECRET, portal=None) -> PortalHmacAuthVerifier:
    return PortalHmacAuthVerifier(secret, portal or StubPortal(), session_ms=SESSION_MS)


def test_accepts_a_well_formed_token():
    claims = verifier().verify_local(make_token("sarath"))
    assert claims is not None
    assert claims.user == "sarath"
    assert claims.role is Role.REALTOR


def test_accepts_an_admin_token():
    claims = verifier().verify_local(make_token("admin", "admin"))
    assert claims is not None and claims.is_admin


def test_username_may_contain_a_pipe():
    """Core.js parses the raw string from the END for exactly this reason: a
    username containing '|' shifts every field if you count from the front."""
    claims = verifier().verify_local(make_token("first|last"))
    assert claims is not None
    assert claims.user == "first|last"
    assert claims.role is Role.REALTOR


def test_rejects_a_forged_signature():
    good = make_token("sarath")
    body, _sig = good.split(".")
    forged = body + "." + make_token("sarath", secret="wrong-key").split(".")[1]
    assert verifier().verify_local(forged) is None


def test_rejects_a_token_signed_with_another_key():
    assert verifier().verify_local(make_token("sarath", secret="other")) is None


def test_rejects_an_expired_token():
    old = int(time.time() * 1000) - SESSION_MS - 1000
    assert verifier().verify_local(make_token("sarath", issued_ms=old)) is None


@pytest.mark.parametrize("bad", ["", "nodot", "a.b.c", "!!.??", "."])
def test_rejects_malformed_tokens(bad):
    assert verifier().verify_local(bad) is None


def test_fails_closed_without_a_secret():
    """No secret must mean no sessions -- never a permissive default."""
    assert PortalHmacAuthVerifier("", StubPortal(), session_ms=SESSION_MS).verify_local(
        make_token("sarath")
    ) is None


async def test_verify_consults_the_portal_for_liveness():
    portal = StubPortal()
    v = verifier(portal=portal)
    assert await v.verify(make_token("sarath")) is not None
    assert portal.calls and portal.calls[0][0] == "session"


async def test_verify_caches_the_liveness_check():
    portal = StubPortal()
    v = verifier(portal=portal)
    tok = make_token("sarath")
    await v.verify(tok)
    await v.verify(tok)
    assert len(portal.calls) == 1


async def test_liveness_cache_evicts_expired_entries():
    """Sessions slide, so tokens are a stream, not a set: an insert-only cache
    grows for as long as the process lives."""
    v = PortalHmacAuthVerifier(
        TEST_SECRET, StubPortal(), session_ms=SESSION_MS, liveness_ttl_s=0.0
    )
    for i in range(50):
        await v.verify(make_token(f"user{i}"))
    assert len(v._seen) <= 1


async def test_liveness_cache_is_capped():
    v = PortalHmacAuthVerifier(
        TEST_SECRET, StubPortal(), session_ms=SESSION_MS, liveness_ttl_s=999.0, max_cached=10
    )
    for i in range(40):
        await v.verify(make_token(f"user{i}"))
    assert len(v._seen) <= 10
