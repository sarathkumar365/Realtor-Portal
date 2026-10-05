"""The chat endpoint: one question in, a stream of events out.

Server-Sent Events rather than a single JSON reply, because the alternative on a
phone is five to ten seconds of blank spinner. SSE is also the reason this
service exists outside Apps Script, which cannot stream at all.
"""

import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import limits
from app.api import container, current_claims
from app.domain import MAX_HISTORY_TURNS, ChatMode, Claims, Turn, Viewer, turns_from

router = APIRouter()
log = logging.getLogger("aura.chat")
audit = logging.getLogger("aura.audit")


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: ChatMode = ChatMode.REALTOR
    conversation_id: str | None = None
    # Client-supplied until the rollout completes. It is the caller's own
    # conversation replayed to the caller's own agent, so it grants no access
    # they do not already have -- but it is still the client asserting what was
    # said, which is why it is capped and why the store replaces it.
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


TITLE_LEN = 60


async def _resolve(store, *, claims: Claims, body: "Ask") -> str | None:
    """The conversation this question belongs to, creating one if needed.

    An id that is not the caller's starts a fresh conversation rather than
    returning None.
    """
    if store is None:
        return None
    if body.conversation_id:
        head = await store.meta(conversation_id=body.conversation_id, user=claims.user)
        if head is not None:
            if head.get("mode") != str(body.mode):
                try:
                    await store.set_mode(
                        conversation_id=body.conversation_id,
                        user=claims.user,
                        mode=str(body.mode),
                    )
                except Exception as exc:
                    log.warning("could not update the mode: %s: %s", type(exc).__name__, exc)
            return body.conversation_id
    return await store.create(
        user=claims.user, title=body.question[:TITLE_LEN], mode=str(body.mode)
    )


async def _history(store, *, cid: str | None, claims: Claims, body: "Ask") -> list[Turn]:
    """Stored turns when there are any, the client's otherwise."""
    if store is None or cid is None:
        return body.history
    return turns_from(await store.history(conversation_id=cid, user=claims.user)) or body.history


def _audit(entry: dict) -> None:
    """One line per question (AUR-20). The question is here; the answer never is."""
    audit.info(json.dumps(entry, separators=(",", ":"), sort_keys=True, default=str))


@router.post("/chat")
async def chat(
    body: Ask, request: Request, claims: Claims = Depends(current_claims)
) -> StreamingResponse:
    """Ask Aura something.

    The mode arrives from the client because it is a UI state, not an account
    property — but nothing downstream trusts the client with it beyond this
    point: it selects a Viewer here, and the repo built from that Viewer is the
    only way the agent can reach project data.
    """
    limits.check(request, "chat", claims.user)
    c = container(request)
    token = request.state.auth_token
    viewer = Viewer.of(claims, body.mode)
    rid = getattr(request.state, "request_id", "-")
    started = time.monotonic()

    async def events() -> AsyncIterator[str]:
        record: dict = {
            "rid": rid,
            "user": claims.user,
            "role": str(claims.role),
            "mode": str(body.mode),
            "question": body.question,
            "conversation_id": None,
            "tools": [],
            "tokens_in": 0,
            "tokens_out": 0,
            "status": "incomplete",
            "error": None,
        }
        try:
            # Everything that can fail happens in here, so every failure reaches
            # the client in the shape it is reading. A misconfigured repo raising
            # out here would 500 with an HTML body to a caller that asked for an
            # event stream.
            try:
                if c.runtime is None:
                    record["status"], record["error"] = "error", "runtime not configured"
                    yield _sse({"type": "error", "detail": "the model is not configured"})
                    return
                repo = c.projects_for(viewer)
            except Exception as exc:
                record["status"], record["error"] = "error", f"{type(exc).__name__}: {exc}"
                log.warning("could not build the repo: %s [rid=%s]", exc, rid)
                yield _sse({"type": "error", "detail": f"{type(exc).__name__}: {exc}"})
                return
            cid, history = None, body.history
            try:
                cid = await _resolve(c.store, claims=claims, body=body)
                history = await _history(c.store, cid=cid, claims=claims, body=body)
            except Exception as exc:
                # `cid` is not reset: a conversation that was created and then
                # lost its history read must still receive the answer, or the
                # row survives with a title and no messages and opens empty.
                log.warning("conversation store unavailable: %s: %s", type(exc).__name__, exc)
                history = body.history
            if cid is not None:
                try:
                    await c.store.append(
                        conversation_id=cid, role="user", message=body.question
                    )
                except Exception as exc:
                    log.warning("could not store the question: %s: %s", type(exc).__name__, exc)
            record["conversation_id"] = cid
            # The mode is echoed first so the UI can prove which one it is in
            # before any content arrives — a realtor must never wonder whether
            # the screen they just turned around is safe.
            yield _sse({"type": "start", "mode": body.mode, "conversation_id": cid})
            answer: list[str] = []
            sources: list[dict] = []
            try:
                async for event in c.runtime.stream(
                    question=body.question,
                    claims=claims,
                    auth=token,
                    mode=body.mode,
                    repo=repo,
                    history=history,
                ):
                    kind = event.get("type")
                    if kind == "text":
                        answer.append(event.get("text") or "")
                    elif kind == "projects":
                        sources = [
                            {"id": p.get("id"), "name": p.get("name")}
                            for p in (event.get("projects") or [])
                            if p.get("id")
                        ]
                    elif kind == "tool":
                        record["tools"].append({"t": event.get("tool")})
                    elif kind == "tool_result":
                        if record["tools"] and "n" not in record["tools"][-1]:
                            record["tools"][-1]["n"] = event.get("count")
                    elif kind == "done":
                        usage = event.get("usage") or {}
                        record["tokens_in"] = usage.get("input_tokens", 0)
                        record["tokens_out"] = usage.get("output_tokens", 0)
                    elif kind == "error":
                        record["status"] = "error"
                        record["error"] = event.get("detail")
                    yield _sse(event)
                if record["status"] == "incomplete":
                    record["status"] = "ok"
            except Exception as exc:
                # The port promises an iterator of events, not that it never
                # raises. A stream that simply stops leaves a conforming client
                # waiting under a finished answer.
                record["status"], record["error"] = "error", f"{type(exc).__name__}: {exc}"
                log.warning("the answer stream failed: %s [rid=%s]", exc, rid)
                yield _sse({"type": "error", "detail": f"{type(exc).__name__}: {exc}"})
            finally:
                if cid is not None and (answer or sources):
                    try:
                        await c.store.append(
                            conversation_id=cid,
                            role="assistant",
                            message="".join(answer),
                            sources=sources,
                        )
                    except Exception as exc:
                        log.warning(
                            "could not store the answer: %s: %s", type(exc).__name__, exc
                        )
        finally:
            record["ms"] = int((time.monotonic() - started) * 1000)
            _audit(record)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Without this an intermediary may buffer the whole response and hand it
        # over at the end, which looks exactly like no streaming at all.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
