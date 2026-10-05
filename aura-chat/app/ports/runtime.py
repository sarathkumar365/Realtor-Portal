from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.domain import ChatMode, Claims, Turn

from .projects import ProjectRepo


class AgentRuntime(Protocol):
    """The model loop: prompt, tool calls, answer. Phase 3.

    Which model answers is configuration inside the runtime, not a port of its
    own -- swapping OpenRouter for Gemini direct is already a model string.
    Swapping the *loop* (PydanticAI for LangGraph, or a hand-rolled one) is what
    this Protocol is for.
    """

    def stream(
        self,
        *,
        question: str,
        claims: Claims,
        auth: str,
        mode: ChatMode,
        repo: ProjectRepo,
        history: list[Turn] | None = None,
    ) -> AsyncIterator[dict]:
        """Answer one question as a sequence of events.

        `repo` is passed in rather than held, because it is built per viewer:
        the runtime must never be able to reach project data the caller has not
        already narrowed to this audience.
        """
        ...

    async def healthy(self) -> bool: ...
