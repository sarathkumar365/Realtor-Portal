"""AgentRuntime on PydanticAI."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app import tools
from app.domain import ChatMode, Claims, Project, Turn
from app.ports import ProjectRepo
from app.prompts import system_prompt

MAX_STEPS = 6
LIMITS = UsageLimits(request_limit=MAX_STEPS)


@dataclass
class Deps:
    """Everything a tool needs, carried through the run."""

    repo: ProjectRepo
    auth: str
    collected: list[Project] = field(default_factory=list)


def _as_messages(history: list[Turn] | None) -> list[Any] | None:
    """Our turns, in the shape the framework wants."""
    if not history:
        return None
    out: list[Any] = []
    for turn in history:
        if turn.role == "user":
            out.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            out.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return out


def _for_model(p: Project) -> dict[str, Any]:
    """One project as the model should see it."""
    out: dict[str, Any] = {"id": p.id, "name": p.name, "city": p.city}
    optional = {
        "builder": p.builder,
        "type": p.property_type,
        "starting_price": p.starting_price,
        "max_price": p.max_price,
        "bedrooms": p.bedrooms,
        "deposit_percent": p.deposit_pct,
        "deposit_schedule": p.deposit_schedule,
        "incentives": p.incentives,
        "occupancy": p.occupancy,
        "address": p.address,
        "last_updated": p.last_updated.isoformat() if p.last_updated else None,
        "source": p.source_url,
        "website_url": p.website_url,
    }
    out.update({k: v for k, v in optional.items() if v not in ("", None)})
    return out


def _for_client(p: Project) -> dict[str, Any]:
    """One project as the PWA's card renderer should see it."""
    return {
        "id": p.id,
        "name": p.name,
        "city": p.city,
        "builder": p.builder,
        "status": p.status,
        "type": p.property_type,
        "starting_price": p.starting_price,
        "occupancy": p.occupancy,
        "depositpct": p.deposit_pct,
        "depositsched": p.deposit_schedule,
        "incentives": p.incentives,
        "last_updated": p.last_updated.isoformat() if p.last_updated else None,
        "broker_url": p.broker_url,
        "drive_url": p.drive_url,
        "website_url": p.website_url,
    }


def build_agent(model: Model | str, *, client_mode: bool, max_tokens: int = 1500) -> Agent:
    agent = Agent(
        model,
        deps_type=Deps,
        instructions=system_prompt(client_mode=client_mode),
        retries=1,
        model_settings=ModelSettings(max_tokens=max_tokens),
    )

    def _keep(ctx: RunContext[Deps], found: list[Project]) -> list[dict[str, Any]]:
        seen = {p.id for p in ctx.deps.collected}
        for p in found:
            if p.id not in seen:
                seen.add(p.id)
                ctx.deps.collected.append(p)
        return [_for_model(p) for p in found]

    @agent.tool
    async def search_projects(
        ctx: RunContext[Deps],
        city: str = "",
        builder: str = "",
        categories: list[str] | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_bedrooms: int | None = None,
        max_deposit_percent: float | None = None,
        occupancy: str = "",
        focus_only: bool | None = None,
        query: str = "",
    ) -> dict[str, Any]:
        """Find projects matching a brief."""
        found = await tools.search_projects(
            ctx.deps.repo,
            auth=ctx.deps.auth,
            city=city,
            builder=builder,
            categories=categories,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            max_deposit_pct=max_deposit_percent,
            occupancy=occupancy,
            focus_only=focus_only,
            query=query,
        )
        return {
            "showing": len(found.items),
            "total": found.total,
            "projects": _keep(ctx, found.items),
        }

    @agent.tool
    async def inventory_summary(
        ctx: RunContext[Deps],
        city: str = "",
        builder: str = "",
        categories: list[str] | None = None,
        focus_only: bool | None = None,
        query: str = "",
        spotlight: str = "none",
    ) -> dict[str, Any]:
        """Counts and names over EVERY match, not a page of them."""
        s = await tools.inventory_summary(
            ctx.deps.repo,
            auth=ctx.deps.auth,
            city=city,
            builder=builder,
            categories=categories,
            focus_only=focus_only,
            query=query,
        )
        out: dict[str, Any] = {
            "total": s.total,
            "names": s.names,
            "cities": [{"city": t.label, "count": t.count} for t in s.cities],
            "builders": [{"builder": t.label, "count": t.count} for t in s.builders],
            "without_a_price": s.without_price,
        }
        if s.names_truncated:
            out["names_note"] = f"first {len(s.names)} names of {s.total}, alphabetical"
        show = spotlight.strip().lower()
        if show not in ("none", "cheapest", "dearest", "both"):
            show = "none"
        if s.cheapest is not None:
            card = show in ("cheapest", "both")
            out["cheapest"] = _keep(ctx, [s.cheapest])[0] if card else _for_model(s.cheapest)
        if s.dearest is not None:
            card = show in ("dearest", "both")
            out["dearest"] = _keep(ctx, [s.dearest])[0] if card else _for_model(s.dearest)
        if s.without_price:
            out["price_caveat"] = (
                f"{s.without_price} of {s.total} have no readable price and are "
                "not represented by cheapest/dearest -- say so"
            )
        return out

    @agent.tool
    async def get_project(ctx: RunContext[Deps], project_id_or_name: str) -> dict[str, Any]:
        """The current record for one project, by id or by its exact name."""
        found = await tools.get_project(ctx.deps.repo, project_id_or_name, auth=ctx.deps.auth)
        if found is not None:
            return {"found": True, **_keep(ctx, [found])[0]}

        near = await tools.search_projects(
            ctx.deps.repo, auth=ctx.deps.auth, query=project_id_or_name
        )
        return {
            "found": False,
            "reason": "no exact id or unique name match",
            "candidates": _keep(ctx, near.items),
            "next": "ask the realtor which of the candidates they mean; do not say the project does not exist",
        }

    @agent.tool
    async def compare_projects(
        ctx: RunContext[Deps], project_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Two or more projects side by side, by id."""
        found = await tools.compare_projects(ctx.deps.repo, project_ids, auth=ctx.deps.auth)
        return _keep(ctx, found)

    @agent.tool
    async def get_recent_projects(ctx: RunContext[Deps], days: int = 7) -> list[dict[str, Any]]:
        """Projects updated in the last N days. Empty means nothing changed."""
        found = await tools.get_recent_projects(ctx.deps.repo, days, auth=ctx.deps.auth)
        return _keep(ctx, found)

    return agent


class PydanticAgentRuntime:
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        model: Model | None = None,
        max_tokens: int = 1500,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._model = model
        self._built: Model | None = None
        self._agents: dict[bool, Agent] = {}

    def _model_for(self) -> Model | str:
        if self._model is not None:
            return self._model
        if self._built is None:
            self._built = OpenAIChatModel(
                self._model_name, provider=OpenRouterProvider(api_key=self._api_key)
            )
        return self._built

    def _agent_for(self, client_mode: bool) -> Agent:
        """Two agents at most: the instructions differ by mode, nothing else."""
        if client_mode not in self._agents:
            self._agents[client_mode] = build_agent(
                self._model_for(), client_mode=client_mode, max_tokens=self._max_tokens
            )
        return self._agents[client_mode]

    async def stream(
        self,
        *,
        question: str,
        claims: Claims,
        auth: str,
        mode: ChatMode,
        repo: ProjectRepo,
        history: list[Turn] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Answer one question, emitting events as they happen."""
        deps = Deps(repo=repo, auth=auth)
        agent = self._agent_for(mode is ChatMode.CLIENT)

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def on_event(ctx, stream) -> None:
            async for ev in stream:
                if isinstance(ev, FunctionToolCallEvent):
                    queue.put_nowait(
                        {"type": "tool", "tool": ev.part.tool_name, "args": ev.part.args_as_dict()}
                    )
                elif isinstance(ev, FunctionToolResultEvent):
                    content = getattr(ev.part, "content", None)
                    queue.put_nowait(
                        {
                            "type": "tool_result",
                            "tool": getattr(ev.part, "tool_name", ""),
                            "count": len(content) if isinstance(content, list) else 1,
                        }
                    )

        async def run() -> None:
            try:
                async with agent.run_stream(
                    question,
                    deps=deps,
                    message_history=_as_messages(history),
                    usage_limits=LIMITS,
                    event_stream_handler=on_event,
                ) as result:
                    async for chunk in result.stream_text(delta=True):
                        if chunk:
                            queue.put_nowait({"type": "text", "text": chunk})
                usage = result.usage
                queue.put_nowait(
                    {"type": "projects", "projects": [_for_client(p) for p in deps.collected]}
                )
                queue.put_nowait(
                    {
                        "type": "done",
                        "usage": {
                            "requests": getattr(usage, "requests", 0),
                            "input_tokens": getattr(usage, "input_tokens", 0),
                            "output_tokens": getattr(usage, "output_tokens", 0),
                        },
                    }
                )
            except Exception as exc:
                queue.put_nowait({"type": "error", "detail": f"{type(exc).__name__}: {exc}"})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def healthy(self) -> bool:
        """Configuration only, deliberately."""
        return bool(self._api_key or self._model is not None)
