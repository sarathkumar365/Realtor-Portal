"""What the model is allowed to do.

Plain async functions over the ports. No framework import, no adapter import,
no knowledge of where data lives -- so the agent framework in agent.py can be
replaced without touching a line here, and so can the data source.

Every tool is read-only by construction: ProjectRepo has no write method to
call (AUR-19).
"""

from app.domain import InventorySummary, Project, ProjectFilters, SearchPage
from app.ports import ProjectRepo

# One question must never drag the whole sheet into a prompt. The model gets the
# records a tool returned and nothing else (AUR-17), so the cap is both a token
# budget and the blast radius of a badly-worded search.
MAX_RESULTS = 12
MAX_COMPARE = 4


# There is no redaction step in this file, deliberately. The repo handed to
# these functions is a RedactingProjectRepo built from the caller's verified
# claims, so an unredacted Project is not something a tool can obtain -- rather
# than something a tool must remember to avoid. See adapters/projects_redacting.
async def search_projects(
    repo: ProjectRepo,
    *,
    auth: str,
    city: str = "",
    builder: str = "",
    categories: list[str] | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    max_deposit_pct: float | None = None,
    occupancy: str = "",
    focus_only: bool | None = None,
    query: str = "",
    limit: int = MAX_RESULTS,
) -> SearchPage:
    """Find projects matching a brief (AUR-25).

    categories are the portal's own buckets: detached, semi, townhome, condo.
    focus_only selects the brokerage's own priority projects.
    """
    filters = ProjectFilters(
        city=city,
        builder=builder,
        categories=categories or [],
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        max_deposit_pct=max_deposit_pct,
        occupancy=occupancy,
        focus_only=focus_only,
        query=query,
        limit=min(limit, MAX_RESULTS),
    )
    return await repo.search(filters, auth=auth)


async def inventory_summary(
    repo: ProjectRepo,
    *,
    auth: str,
    city: str = "",
    builder: str = "",
    categories: list[str] | None = None,
    focus_only: bool | None = None,
    query: str = "",
) -> InventorySummary:
    """Counts and names over everything that matches, not a page of it (AUR-29).

    Same filters as `search_projects` and the same `matches` behind them, so the
    two can never describe different sets. No `limit`: a summary that could be
    truncated would be the bug it exists to fix.
    """
    filters = ProjectFilters(
        city=city,
        builder=builder,
        categories=categories or [],
        focus_only=focus_only,
        query=query,
    )
    return await repo.summarise(filters, auth=auth)


async def get_project(repo: ProjectRepo, ref: str, *, auth: str) -> Project | None:
    """One project's current record, by id or by exact name (AUR-26).

    A realtor naming a project is not handing over an id, and a model asked
    "what's the deposit for Reva Westfield?" will pass the name. Refusing that
    made Aura answer "no such project" about projects that plainly exist, so
    the name is resolved here rather than left to the caller to get right.

    An ambiguous name returns None, never a guess. Two Brampton projects are
    both called "Mayfield Village"; picking one would produce a confident answer
    about the wrong builder's deposit schedule.
    """
    ref = ref.strip()
    if not ref:
        return None
    found = await repo.get(ref, auth=auth)
    if found is not None:
        return found
    # Search rather than scan: filtering belongs behind the port.
    candidates = await repo.search(
        ProjectFilters(query=ref, include_unavailable=True, limit=MAX_RESULTS), auth=auth
    )
    exact = [p for p in candidates.items if p.name.strip().lower() == ref.lower()]
    return exact[0] if len(exact) == 1 else None


async def compare_projects(
    repo: ProjectRepo, project_ids: list[str], *, auth: str
) -> list[Project]:
    """Several projects side by side (AUR-27).

    Returns records, not prose: the table is the answer, and letting the model
    restate numbers is how numbers drift.
    """
    found = [await repo.get(pid, auth=auth) for pid in project_ids[:MAX_COMPARE]]
    return [p for p in found if p is not None]


async def get_recent_projects(
    repo: ProjectRepo,
    days: int = 7,
    *,
    auth: str,
    limit: int = MAX_RESULTS,
) -> list[Project]:
    """What changed lately (AUR-28).

    Ordered by the sheet's own LAST UPDATED, so it is only as honest as that
    column. An unfilled column means an empty answer, which is the correct
    answer -- not a guess from cache timestamps.
    """
    return await repo.recent(days, auth=auth, limit=min(limit, MAX_RESULTS))
