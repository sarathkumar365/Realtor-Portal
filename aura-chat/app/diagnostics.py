"""Self-checks for the service and everything it depends on.

Two audiences, so two depths:

* `/health` -- the platform's liveness probe. Cheap, public, and deliberately
  uninformative: a public endpoint should not tell a stranger which of our
  secrets is unset.
* `/doctor` -- a signed-in human trying to work out why an answer failed. It
  runs the checks that need a real token, including an actual read of project
  data, because "the portal is reachable" and "Aura can read projects" are
  different claims and only the second one matters to a realtor.

Depends on the container and the ports; never on an adapter.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from app.container import Container
from app.domain import Claims


@dataclass(slots=True)
class Check:
    name: str
    ok: bool | None  # None = not applicable yet (a phase that has not shipped)
    detail: str = ""
    ms: int | None = None
    # A failing optional check degrades the service without breaking it: losing
    # history is an annoyance, losing project data is an outage.
    critical: bool = True

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.detail:
            out["detail"] = self.detail
        if self.ms is not None:
            out["ms"] = self.ms
        if not self.critical:
            out["critical"] = False
        return out


@dataclass(slots=True)
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        crit = [c for c in self.checks if c.critical and c.ok is not None]
        if any(c.ok is False for c in crit):
            return "down"
        if any(c.ok is False for c in self.checks):
            return "degraded"
        return "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.status == "ok",
            "checks": {c.name: c.as_dict() for c in self.checks},
        }


async def _timed(name: str, coro, *, critical: bool = True, expect: str = "") -> Check:
    started = time.monotonic()
    try:
        ok = bool(await coro)
        detail = "" if ok else (expect or "check returned false")
    except Exception as exc:  # a dependency's failure must not 500 the doctor
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return Check(name, ok, detail, int((time.monotonic() - started) * 1000), critical)


def config_check(c: Container) -> Check:
    """Which settings are missing -- by name, never by value."""
    missing = [
        name
        for name, present in (
            ("TOKEN_SECRET", c.settings.auth_ready),
            ("EXEC_URL", c.settings.portal_ready),
        )
        if not present
    ]
    return Check(
        "config",
        not missing,
        detail="missing: " + ", ".join(missing) if missing else "",
    )


async def shallow(c: Container) -> Report:
    """What `/health` runs. No token, so no data-plane check is possible --
    every portal action but login/session requires one."""
    checks = [config_check(c)]
    if c.settings.portal_ready:
        checks.append(
            await _timed(
                "portal_reachable",
                c.portal.healthy(),
                expect="exec URL did not answer with JSON",
            )
        )
    else:
        checks.append(Check("portal_reachable", None, "EXEC_URL not set"))
    checks.append(
        await _timed("model", c.runtime.healthy())
        if c.runtime is not None
        else Check("model", None, "not wired yet")
    )
    return Report(checks)


async def deep(c: Container, *, auth: str, claims: Claims | None, fresh: bool = False) -> Report:
    """What /doctor runs: everything in shallow(), plus the checks that need a
    token.

    `claims` is None when the presented token did not verify here. That is not
    a reason to refuse: it is the single most valuable thing this can diagnose,
    and a doctor that stops working when the patient is sick is no use. The
    report continues, with detail redacted everywhere except the two checks
    that explain the refusal.
    """
    report = await shallow(c)

    # Proves the portal accepts this token. Read together with the local
    # verification below, it separates the two failures that look identical
    # from the outside: our key being wrong, and the token being stale.
    portal_auth = await _timed(
        "portal_auth",
        _portal_auth(c, auth),
        expect="the portal refused this token",
    )
    report.checks.append(portal_auth)
    report.checks.append(_token_check(claims, portal_auth.ok))

    # The claim that actually matters: can Aura read project data right now?
    if c.projects is None:
        report.checks.append(Check("project_data", None, "not wired yet"))
    else:
        report.checks.append(
            await _timed(
                "project_data", _project_probe(c, auth, fresh), expect="no projects returned"
            )
        )

    report.checks.append(
        await _timed("conversation_store", c.store.healthy(), critical=False)
        if c.store is not None
        else Check("conversation_store", None, "not wired yet", critical=False)
    )
    report.checks.append(
        await _timed("document_index", c.documents.healthy(), critical=False)
        if c.documents is not None
        else Check("document_index", None, "not wired yet", critical=False)
    )
    report.checks.append(data_quality(c))
    if claims is None:
        _redact(report)
    return report


# Only these two may speak freely to a caller whose token did not verify: they
# are the diagnosis, and neither reveals anything a stranger can use.
_ALWAYS_DETAILED = {"token_verification", "portal_auth"}


def _redact(report: Report) -> None:
    for check in report.checks:
        if check.name not in _ALWAYS_DETAILED:
            check.detail = ""


def _token_check(claims: Claims | None, portal_accepted: bool | None) -> Check:
    """The one diagnosis that is otherwise a whole afternoon.

    A mismatched TOKEN_SECRET looks exactly like an expired session from the
    outside -- every realtor gets 401 while /health stays green. The portal's
    own verdict is what tells the two apart.
    """
    if claims is not None:
        return Check("token_verification", True, f"verified as {claims.user}")
    if portal_accepted:
        return Check(
            "token_verification",
            False,
            "the portal accepts this token but this service cannot verify it -- "
            "TOKEN_SECRET does not match the Script Property in the Apps Script project",
        )
    return Check(
        "token_verification",
        False,
        "neither this service nor the portal accepts this token -- it is expired, "
        "revoked, or not a portal token",
    )


async def _portal_auth(c: Container, auth: str) -> bool:
    data = await c.portal.call("session", auth=auth)
    return bool(data.get("ok"))


async def _project_probe(c: Container, auth: str, fresh: bool = False) -> bool:
    from app.domain import STRICTEST, ProjectFilters

    if fresh:
        return await c.projects.refresh(auth=auth) > 0
    # Through the redacting wrapper, and at the strictest setting: a check that
    # takes a shortcut past the layer it is meant to prove stops being a check.
    repo = c.projects_for(STRICTEST)
    return len((await repo.search(ProjectFilters(limit=1), auth=auth)).items) > 0


def data_quality(c: Container) -> Check:
    """How much of what came back was actually usable.

    A price the parser could not read is not an error -- it is a project that
    silently drops out of every price filter. Counting them here means a change
    in how prices are written shows up as a number, rather than as a realtor
    getting an answer that quietly omits half the projects.
    """
    repo = c.projects
    total = getattr(repo, "total_rows", 0)
    unparsed = getattr(repo, "unparsed_prices", 0)
    rollup = getattr(repo, "skipped_rollup_rows", 0)
    future = getattr(repo, "future_dated", 0)
    if not total:
        return Check("data_quality", None, "no projects read yet", critical=False)
    detail = f"{total} projects"
    if unparsed:
        detail += f", {unparsed} with a price the parser could not read"
    if rollup:
        detail += f", {rollup} roll-up rows skipped"
    if future:
        detail += f", {future} dated in the future"
    return Check("data_quality", unparsed == 0 and future == 0, detail, critical=False)
