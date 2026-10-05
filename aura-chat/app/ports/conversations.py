from typing import Protocol


class ConversationStore(Protocol):
    """Chat history and the feedback derived from it. Phase 4.

    Feedback lives here rather than on a sixth port: it is data *about* a
    conversation, and the port count is a hard cap of five.

    Every read takes `user` and is expected to filter on it. A conversation_id
    is a label, not a capability -- an id that leaked to another realtor must
    not open the thread (AUR-40).

    `meta` answers both questions about a thread the caller did not just create
    -- may I write to it, and what mode was it held in -- in one round trip.
    """

    async def create(self, *, user: str, title: str, mode: str = "realtor") -> str: ...

    async def append(
        self,
        *,
        conversation_id: str,
        role: str,
        message: str,
        sources: list[dict] | None = None,
    ) -> str: ...

    async def history(
        self, *, conversation_id: str, user: str, limit: int = 20
    ) -> list[dict]: ...

    async def list_for(self, *, user: str, limit: int = 30) -> list[dict]: ...

    async def meta(self, *, conversation_id: str, user: str) -> dict | None: ...

    async def set_mode(self, *, conversation_id: str, user: str, mode: str) -> None: ...

    async def record_feedback(self, *, user: str, entry: dict) -> None: ...

    async def list_feedback(self, *, limit: int = 100) -> list[dict]: ...

    async def healthy(self) -> bool: ...
