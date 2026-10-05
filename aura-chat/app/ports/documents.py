from typing import Protocol


class DocumentIndex(Protocol):
    """Retrieval over project documents. Phase 5.

    Only current documents are ever returned: an April price list must never
    come back beside August's (AUR-30). That rule lives in the adapter, so it
    cannot be forgotten by a caller.
    """

    async def query(
        self, text: str, *, project_id: str | None = None, client_safe: bool = False, k: int = 5
    ) -> list[dict]: ...

    async def healthy(self) -> bool: ...
