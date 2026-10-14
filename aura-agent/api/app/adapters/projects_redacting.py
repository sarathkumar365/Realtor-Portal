"""A ProjectRepo that can only hand out what its viewer may see.

The point is not that it filters -- `_present()` in tools.py filtered too. The
point is that filtering is no longer **opt-in**. Tools are given this object and
never the one underneath, so there is no code path that yields an unredacted
Project, and a tool added in a hurry cannot forget to call anything.

That matters because the failure is silent: a realtor turns their phone toward
a buyer, commission is on screen, and nothing errors, logs, or can be undone.

Constructed per request, from the verified claims plus the conversation's mode
(AUR-18, AUR-55, AUR-56).
"""

from app.domain import InventorySummary, Project, ProjectFilters, SearchPage, Viewer
from app.ports import ProjectRepo


class RedactingProjectRepo:
    def __init__(self, inner: ProjectRepo, viewer: Viewer) -> None:
        self._inner = inner
        self._viewer = viewer

    def _redact(self, projects: list[Project]) -> list[Project]:
        return [p.for_viewer(self._viewer) for p in projects]

    async def search(self, filters: ProjectFilters, *, auth: str) -> SearchPage:
        # Filtering runs on the UNREDACTED records inside `_inner`, which is
        # correct: a search is allowed to *use* a field it may not *show*. What
        # a viewer sees is a separate question from what the sheet knows, and
        # conflating them would quietly change results by mode.
        #
        # `total` is deliberately NOT redacted down. It counts what matched, and
        # what matched does not change with the audience -- only which fields of
        # it are shown. Recomputing it per viewer would make the same search
        # report different inventory in Client Mode.
        page = await self._inner.search(filters, auth=auth)
        return SearchPage(items=self._redact(page.items), total=page.total)

    async def summarise(self, filters: ProjectFilters, *, auth: str) -> InventorySummary:
        # Counts, names, cities and builders are visible to every audience, so
        # only the two embedded Projects need redacting -- and they need it for
        # the same reason any other card does.
        s = await self._inner.summarise(filters, auth=auth)
        return s.model_copy(update={
            "cheapest": s.cheapest.for_viewer(self._viewer) if s.cheapest else None,
            "dearest": s.dearest.for_viewer(self._viewer) if s.dearest else None,
        })

    async def get(self, project_id: str, *, auth: str) -> Project | None:
        found = await self._inner.get(project_id, auth=auth)
        return self._redact([found])[0] if found else None

    async def recent(self, days: int, *, auth: str, limit: int = 20) -> list[Project]:
        return self._redact(await self._inner.recent(days, auth=auth, limit=limit))

    async def refresh(self, *, auth: str) -> int:
        return await self._inner.refresh(auth=auth)

    async def healthy(self) -> bool:
        return await self._inner.healthy()

    # Diagnostics read these off whatever repo they are handed, so they have to
    # survive the wrapper.
    @property
    def total_rows(self) -> int:
        return getattr(self._inner, "total_rows", 0)

    @property
    def unparsed_prices(self) -> int:
        return getattr(self._inner, "unparsed_prices", 0)

    @property
    def skipped_rollup_rows(self) -> int:
        return getattr(self._inner, "skipped_rollup_rows", 0)

    @property
    def future_dated(self) -> int:
        return getattr(self._inner, "future_dated", 0)
