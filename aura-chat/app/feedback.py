"""Feedback: writing it, and reading it back as the data owner (AUR-61, 62)."""

import csv
import io
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.api import container, current_claims
from app.domain import Claims, Feedback

router = APIRouter()

MAX_REVIEW = 500

UNAVAILABLE = "the report queue is unavailable"

log = logging.getLogger("aura.feedback")


def _record(entry: dict) -> None:
    """The audit line. Kept after the table exists, because AUR-20 wants request and audit
    logging and "who reported what, when" is exactly that.
    """
    log.info(json.dumps(entry, separators=(",", ":"), sort_keys=True))


@router.post("/feedback")
async def feedback(body: Feedback, request: Request, claims: Claims = Depends(current_claims)) -> dict:
    """Record a thumbs up or down, and optionally a data issue."""
    entry = {
        "answer_id": body.answer_id,
        "user": claims.user,
        "role": str(claims.role),
        "verdict": str(body.verdict) if body.verdict else None,
        "category": str(body.category) if body.category else None,
        "question": body.question,
        "note": body.note,
        "project_ids": body.project_ids,
    }
    _record(entry)
    store = container(request).store
    if store is not None:
        try:
            await store.record_feedback(user=claims.user, entry=entry)
        except Exception as exc:
            log.warning("could not store feedback: %s: %s", type(exc).__name__, exc)
    return {"ok": True}


def _reviewer(request: Request, claims: Claims):
    """The store, for a caller entitled to read everyone's reports."""
    if not claims.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    store = container(request).store
    if store is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return store


async def _queue(request: Request, claims: Claims, limit: int) -> list[dict]:
    store = _reviewer(request, claims)
    try:
        return await store.list_feedback(limit=min(max(limit, 1), MAX_REVIEW))
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("could not read the report queue: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from exc


@router.get("/feedback")
async def review(
    request: Request, limit: int = 100, claims: Claims = Depends(current_claims)
) -> dict:
    """Reported issues, newest first. Admin only."""
    return {"feedback": await _queue(request, claims, limit)}


CSV_COLUMNS = (
    "created_at", "user_id", "verdict", "category", "question", "note", "project_ids"
)

FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _inert(value: str) -> str:
    """Text a spreadsheet will show rather than run. The quote is consumed on
    display."""
    text = str(value)
    return "'" + text if text.startswith(FORMULA_LEAD) else text


@router.get("/feedback.csv", response_class=PlainTextResponse)
async def review_csv(
    request: Request, limit: int = 500, claims: Claims = Depends(current_claims)
) -> PlainTextResponse:
    """The same queue as a spreadsheet. Column order is fixed."""
    rows = await _queue(request, claims, limit)
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(CSV_COLUMNS)
    for r in rows:
        out.writerow(
            [
                _inert(" ".join(str(x) for x in (r.get(c) or [])))
                if c == "project_ids"
                else _inert(r.get(c) or "")
                for c in CSV_COLUMNS
            ]
        )
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aura-reports.csv"'},
    )
