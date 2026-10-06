"""Reading conversations back. Writes happen in chat.py as a side effect of answering."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api import container, current_claims
from app.domain import Claims

router = APIRouter()
log = logging.getLogger("aura.conversations")

MAX_LIST = 50

MAX_MESSAGES = 200

UNAVAILABLE = "conversation history is unavailable"


def _store(request: Request):
    c = container(request)
    if c.store is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return c.store


def _down(exc: Exception) -> HTTPException:
    log.warning("conversation store unavailable: %s: %s", type(exc).__name__, exc)
    return HTTPException(status_code=503, detail=UNAVAILABLE)


@router.get("/conversations")
async def list_conversations(
    request: Request, limit: int = 30, claims: Claims = Depends(current_claims)
) -> dict:
    """This realtor's threads, newest first."""
    try:
        rows = await _store(request).list_for(
            user=claims.user, limit=min(max(limit, 1), MAX_LIST)
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _down(exc) from exc
    return {"conversations": rows}


@router.get("/conversations/{conversation_id}")
async def read_conversation(
    conversation_id: str, request: Request, claims: Claims = Depends(current_claims)
) -> dict:
    """One thread: its head row and its messages, oldest first."""
    store = _store(request)
    try:
        head = await store.meta(conversation_id=conversation_id, user=claims.user)
    except Exception as exc:
        raise _down(exc) from exc
    if head is None:
        raise HTTPException(status_code=404, detail="no such conversation")
    try:
        rows = await store.history(
            conversation_id=conversation_id, user=claims.user, limit=MAX_MESSAGES
        )
    except Exception as exc:
        raise _down(exc) from exc
    return {
        "conversation_id": conversation_id,
        "title": head.get("title", ""),
        "mode": head.get("mode", "realtor"),
        "messages": rows,
    }
