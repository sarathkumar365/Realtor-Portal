"""HTTP surface. Routes depend on ports via the container, never on adapters."""

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app import diagnostics, limits
from app.container import Container
from app.domain import Claims, Organization

router = APIRouter()
log = logging.getLogger("aura.auth")


def container(request: Request) -> Container:
    return request.app.state.container


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def presented_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    """The token as sent, verified or not."""
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="login required")
    request.state.auth_token = token
    return token


async def current_claims(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Claims:
    """Bearer token -> verified identity, or 401."""
    c = container(request)
    token = _bearer(authorization)
    if not token:
        raise _rejected(request, "no bearer token")
    claims = await c.auth.verify(token)
    if claims is None:
        raise _rejected(request, "token did not verify")
    request.state.auth_token = token
    return claims


def _rejected(request: Request, why: str) -> HTTPException:
    """A refused request, logged (AUR-20). The reason and the address, never the
    token."""
    log.info(
        "auth refused: %s ip=%s path=%s rid=%s",
        why,
        limits.client_ip(request),
        request.url.path,
        getattr(request.state, "request_id", "-"),
    )
    return HTTPException(status_code=401, detail="login required")


class Credentials(BaseModel):
    user: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
async def login(body: Credentials, request: Request) -> dict:
    """Sign in with portal credentials and get back a session token."""
    limits.check(request, "login", limits.client_ip(request))
    c = container(request)
    try:
        data = await c.portal.call("login", user=body.user, password=body.password)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"portal unreachable: {exc}") from exc
    if not data.get("ok"):
        raise HTTPException(status_code=401, detail=data.get("error") or "invalid id or password")
    token = data.get("token")
    if not token:
        raise HTTPException(
            status_code=502, detail="portal accepted the sign-in but returned no token"
        )
    return {
        "ok": True,
        "token": token,
        "name": data.get("name", body.user),
        "role": data.get("role", "realtor"),
    }


@router.get("/health")
async def health(request: Request) -> dict:
    """Liveness and readiness, for the platform's probe."""
    report = await diagnostics.shallow(container(request))
    return {"status": report.status, "ok": report.status != "down"}


@router.get("/doctor")
async def doctor(
    request: Request, fresh: bool = False, token: str = Depends(presented_token)
) -> dict:
    """Full diagnosis, for a signed-in human working out why an answer failed."""
    limits.check(request, "doctor", limits.client_ip(request))
    c = container(request)
    claims = await c.auth.verify(token)
    report = await diagnostics.deep(c, auth=token, claims=claims, fresh=fresh)
    return {**report.as_dict(), "user": claims.user if claims else None}


@router.get("/me")
async def me(claims: Claims = Depends(current_claims)) -> dict:
    """Proves the auth path end to end without touching project data."""
    return {"user": claims.user, "role": claims.role, "admin": claims.is_admin}


def _admin_only(claims: Claims) -> None:
    if not claims.is_admin:
        raise HTTPException(status_code=403, detail="admin only")


@router.get("/admin/organization")
async def get_organization(request: Request, claims: Claims = Depends(current_claims)) -> dict:
    """The profile in use: the saved one, or the defaults. Admin only."""
    _admin_only(claims)
    return container(request).organization.model_dump(mode="json")


@router.put("/admin/organization")
async def put_organization(
    body: Organization, request: Request, claims: Claims = Depends(current_claims)
) -> dict:
    """Save the profile and use it at once, in chat and in every new Unbrander job.
    Jobs already uploaded keep the profile they were given. Admin only."""
    _admin_only(claims)
    c = container(request)
    if c.organization_store is None:
        raise HTTPException(status_code=503, detail="no database is configured")
    try:
        await c.save_organization(body, by=claims.user)
    except Exception as exc:
        log.warning("could not save the organization: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=503, detail="could not save the profile") from exc
    logging.getLogger("aura.audit").info(json.dumps(
        {"event": "organization saved", "user": claims.user, "name": body.name}))
    return body.model_dump(mode="json")
