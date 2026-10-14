from typing import Protocol

from app.domain import InventorySummary, Project, ProjectFilters, SearchPage


class ProjectRepo(Protocol):
    """Project data, wherever it lives.

    Filtering, sorting and limiting all happen behind this port. A caller that
    fetches everything and filters it itself works today -- the sheet returns
    everything anyway -- and silently blocks the move to SQL, where the same
    filter should become a WHERE clause.
    """

    async def search(self, filters: ProjectFilters, *, auth: str) -> SearchPage:
        """Matching projects, capped by `filters.limit`, plus how many matched.

        The count is part of the port rather than a second call because it is
        free where the filtering happens -- `len(hits)` in the sheet adapter, a
        window function in SQL -- and a caller that has to ask for it separately
        is a caller that will forget.
        """
        ...

    async def summarise(self, filters: ProjectFilters, *, auth: str) -> InventorySummary:
        """Counts and names over every match, ignoring `filters.limit`.

        Deliberately a method here rather than something a caller assembles from
        `search`: a caller that raises the limit to count is a caller that pulls
        the whole sheet into a prompt, and in SQL this is GROUP BY rather than a
        second full read.
        """
        ...

    async def get(self, project_id: str, *, auth: str) -> Project | None: ...

    async def recent(self, days: int, *, auth: str, limit: int = 20) -> list[Project]: ...

    async def refresh(self, *, auth: str) -> int:
        """Drop any caching and re-read, returning how many projects came back.

        A capability, not a leak of how the adapter stores things: a repo with
        no cache implements this as an ordinary read. It exists because a sheet
        edit is invisible until a cache turns over, and 'wait six hours' is not
        an answer during a sprint.
        """
        ...

    async def healthy(self) -> bool: ...
