"""The containment boundary: sheet shapes in, domain objects out.

If any of these start needing knowledge of a column name outside this file, the
"move to a database" migration has stopped being a one-file change.
"""

import pytest

from app.adapters.portal_client import PortalError
from app.adapters.projects_exec import ExecApiProjectRepo
from app.domain import ProjectFilters

AUTH = "tok"


def row(**over) -> dict:
    base = {
        "city": "BRAMPTON", "row": 3, "id": "AK-0001", "project": "Reva Westfield",
        "builder": "Great Gulf", "type": "Townhome", "cats": ["townhome"],
        "status": "Available", "hidden": False, "focus": False,
        "occupancy": "2027", "address": "12 Main St",
        "price": "$899,900", "maxprice": "", "beds": "3-4",
        "depositpct": "10%", "depositsched": "5% on signing", "incentives": "Free upgrades",
        "lastupdated": "2026-08-24", "sourceurl": "https://example/x",
        "website_url": "https://public/x", "drive_url": "", "broker_url": "https://portal/x",
        "login": "agent@builder", "office": "905", "contact": "Rep", "fub": "tpl",
    }
    base.update(over)
    return base


class StubPortal:
    def __init__(self, rows=None, payload=None):
        self.rows = rows if rows is not None else [row()]
        self.payload = payload
        self.fetches = 0

    async def call(self, action, *, auth=None, **params):
        self.fetches += 1
        if self.payload is not None:
            return self.payload
        return {"updated": "now", "count": len(self.rows), "rows": self.rows}

    async def healthy(self):
        return True


def repo(portal, **kw) -> ExecApiProjectRepo:
    return ExecApiProjectRepo(portal, **kw)


async def test_a_sheet_row_becomes_a_domain_project():
    out = (await repo(StubPortal()).search(ProjectFilters(), auth=AUTH)).items
    p = out[0]
    assert p.id == "AK-0001"
    assert p.name == "Reva Westfield"
    assert p.starting_price == 899_900   # parsed from "$899,900"
    assert p.min_bedrooms == 3           # parsed from "3-4"
    assert p.deposit_pct == 10.0
    assert p.last_updated.isoformat() == "2026-08-24"


async def test_a_missing_project_id_falls_back_to_a_slug():
    """Sudhanshu is filling the real column now; deep links work meanwhile."""
    out = (await repo(StubPortal([row(id="")])).search(ProjectFilters(), auth=AUTH)).items
    assert out[0].id == "brampton:reva-westfield"


async def test_a_real_project_id_always_wins_over_the_slug():
    out = (await repo(StubPortal([row(id="AK-0042")])).search(ProjectFilters(), auth=AUTH)).items
    assert out[0].id == "AK-0042"


async def test_rows_without_a_name_or_city_are_dropped():
    portal = StubPortal([row(project=""), row(city=""), row()])
    assert len((await repo(portal).search(ProjectFilters(), auth=AUTH)).items) == 1


async def test_columns_a_tab_does_not_have_read_as_absent_not_wrong():
    """Every tab but BRAMPTON lacks the commercial columns today."""
    bare = {k: "" for k in row()}
    bare.update({"city": "AJAX", "project": "Somewhere", "cats": [], "hidden": False})
    out = (await repo(StubPortal([bare])).search(ProjectFilters(), auth=AUTH)).items
    p = out[0]
    assert p.starting_price is None and p.deposit_pct is None and p.last_updated is None


async def test_the_index_is_cached_across_searches():
    portal = StubPortal()
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    await r.search(ProjectFilters(city="BRAMPTON"), auth=AUTH)
    await r.get("AK-0001", auth=AUTH)
    assert portal.fetches == 1


async def test_an_expired_cache_refetches():
    portal = StubPortal()
    r = repo(portal, ttl_s=0.0)
    await r.search(ProjectFilters(), auth=AUTH)
    await r.search(ProjectFilters(), auth=AUTH)
    assert portal.fetches == 2


async def test_invalidate_forces_a_refetch():
    portal = StubPortal()
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    r.invalidate()
    await r.search(ProjectFilters(), auth=AUTH)
    assert portal.fetches == 2


async def test_a_refused_index_raises_rather_than_caching_an_empty_set():
    """Caching a refusal would serve 'no projects found' for five minutes --
    indistinguishable, to a realtor, from the sheet being empty."""
    r = repo(StubPortal(payload={"ok": False, "error": "login required"}))
    with pytest.raises(PortalError):
        await r.search(ProjectFilters(), auth=AUTH)


async def test_unparsed_prices_are_counted_for_diagnosis():
    """A spike means Sudhanshu has started writing prices a new way, and we
    should hear it from /doctor rather than from a wrong answer."""
    portal = StubPortal([row(price="ask us"), row(price="$1,000,000")])
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    assert r.unparsed_prices == 1
    assert r.total_rows == 2


async def test_get_finds_an_unavailable_project_that_search_hides():
    """'What happened to X?' still needs an answer."""
    portal = StubPortal([row(hidden=True)])
    r = repo(portal)
    assert (await r.search(ProjectFilters(), auth=AUTH)).items == []
    assert (await r.get("AK-0001", auth=AUTH)) is not None


async def test_recent_returns_the_most_recently_updated_first():
    portal = StubPortal(
        [
            row(id="old", project="Old", lastupdated="2026-01-01"),
            row(id="new", project="New", lastupdated="2026-08-24"),
            row(id="none", project="Undated", lastupdated=""),
        ]
    )
    out = await repo(portal).recent(365, auth=AUTH)
    assert [p.id for p in out] == ["new", "old"]


async def test_recent_excludes_future_dates_and_counts_them():
    """A date after today is a typo, not a change. Without the bound the
    descending sort ranks it first, every week, until it arrives."""
    from datetime import date, timedelta

    portal = StubPortal(
        [
            row(id="now", project="Now", lastupdated=date.today().isoformat()),
            row(
                id="typo",
                project="Typo",
                lastupdated=(date.today() + timedelta(days=60)).isoformat(),
            ),
        ]
    )
    r = repo(portal)
    assert [p.id for p in await r.recent(7, auth=AUTH)] == ["now"]
    assert r.future_dated == 1


async def test_get_ignores_id_case():
    portal = StubPortal([row(id="AK-0002", project="Cornerstone")])
    found = await repo(portal).get("ak-0002", auth=AUTH)
    assert found is not None and found.id == "AK-0002"


async def test_get_prefers_the_exact_id_over_a_case_variant():
    """Two rows whose ids differ only by case must not shadow each other for a
    caller who typed the id exactly."""
    portal = StubPortal(
        [row(id="ak-0002", project="Slugged"), row(id="AK-0002", project="Explicit")]
    )
    found = await repo(portal).get("AK-0002", auth=AUTH)
    assert found is not None and found.name == "Explicit"


async def test_recent_says_nothing_when_the_column_is_unfilled():
    """An empty answer is correct here. Falling back to cache timestamps would
    invent a freshness the sheet never claimed."""
    portal = StubPortal([row(lastupdated="")])
    assert await repo(portal).recent(7, auth=AUTH) == []


async def test_refresh_bypasses_both_caches():
    """A sheet edit is invisible until a cache turns over, and the portal's is
    six hours. 'Wait until this evening' is not an answer during a sprint."""
    portal = StubPortal()
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    assert portal.fetches == 1
    assert await r.refresh(auth=AUTH) == 1
    assert portal.fetches == 2


async def test_refresh_asks_the_portal_to_rebuild_too():
    """Bypassing only our cache would re-read the portal's stale copy."""
    seen = []

    class Recording(StubPortal):
        async def call(self, action, *, auth=None, **params):
            seen.append(params)
            return await super().call(action, auth=auth, **params)

    await repo(Recording()).refresh(auth=AUTH)
    assert seen[0].get("fresh") is True


async def test_recent_is_measured_from_today_not_from_the_newest_row():
    """A sheet nobody has touched for months has no recent changes.

    Anchoring the window to the newest row instead would report six-week-old
    edits as "what changed this week" -- freshness the sheet never claimed --
    and would make an empty answer impossible.
    """
    from datetime import date, timedelta

    old = (date.today() - timedelta(days=100)).isoformat()
    older = (date.today() - timedelta(days=104)).isoformat()
    portal = StubPortal(
        [row(id="a", project="A", lastupdated=old), row(id="b", project="B", lastupdated=older)]
    )
    assert await repo(portal).recent(7, auth=AUTH) == []


async def test_recent_still_finds_genuinely_recent_changes():
    from datetime import date, timedelta

    portal = StubPortal(
        [
            row(id="new", project="New", lastupdated=date.today().isoformat()),
            row(id="old", project="Old", lastupdated=(date.today() - timedelta(days=90)).isoformat()),
        ]
    )
    assert [p.id for p in await repo(portal).recent(7, auth=AUTH)] == ["new"]


async def test_a_range_in_one_price_column_keeps_both_ends():
    """ONTARIO carries PRICE RANGE in a single column. Losing the high end
    excludes a project selling up to $1.4M from an 'at least $1M' search."""
    portal = StubPortal([row(price="$800,000 - $1,400,000", maxprice="")])
    p = (await repo(portal).search(ProjectFilters(), auth=AUTH)).items[0]
    assert p.starting_price == 800_000
    assert p.max_price == 1_400_000


async def test_an_explicit_max_price_column_still_wins():
    portal = StubPortal([row(price="$800,000", maxprice="$1,100,000")])
    p = (await repo(portal).search(ProjectFilters(), auth=AUTH)).items[0]
    assert (p.starting_price, p.max_price) == (800_000, 1_100_000)


async def test_placeholder_prices_are_not_counted_as_parser_failures():
    """TBD is correct data entry. Counting it buries the signal this exists to
    give -- a real change in how prices are written."""
    portal = StubPortal([row(price="TBD"), row(price="N/A"), row(price="$1,000,000")])
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    assert r.unparsed_prices == 0


async def test_a_genuinely_unreadable_price_is_still_counted():
    portal = StubPortal([row(price="somewhere around a million")])
    r = repo(portal)
    await r.search(ProjectFilters(), auth=AUTH)
    assert r.unparsed_prices == 1


async def test_the_ontario_rollup_tab_never_becomes_projects():
    """Its rows are second copies, and the copies disagree with the originals.

    Caledon Club is 2027/2028 and a focus project on the CALEDON tab, 2026 and
    not a focus project on ONTARIO. Both reached the model as separate projects,
    so either occupancy could be quoted as fact.
    """
    portal = StubPortal([
        row(city="CALEDON", id="", project="Caledon Club", occupancy="2027/2028", focus=True),
        row(city="ONTARIO", id="", project="Caledon Club", occupancy="2026", focus=False),
    ])
    out = (await repo(portal).search(ProjectFilters(), auth=AUTH)).items
    assert [p.city for p in out] == ["CALEDON"]
    assert out[0].occupancy == "2027/2028"


async def test_skipped_rollup_rows_are_counted_for_doctor():
    r = repo(StubPortal([row(), row(city="ONTARIO"), row(city="ontario")]))
    await r.search(ProjectFilters(), auth=AUTH)
    assert r.skipped_rollup_rows == 2   # matched case-insensitively
    assert r.total_rows == 1


async def test_a_summary_drops_blank_builders_rather_than_counting_them():
    """An unfilled BUILDER column is not a builder named "". Counting it would
    put an unnamed bucket at the top of a list read as "who we work with"."""
    portal = StubPortal([
        row(project="A", builder="Great Gulf"),
        row(project="B", builder="Great Gulf"),
        row(project="C", builder=""),
    ])
    s = await repo(portal).summarise(ProjectFilters(), auth=AUTH)
    assert s.total == 3
    assert [(t.label, t.count) for t in s.builders] == [("Great Gulf", 2)]


async def test_a_summary_ignores_the_limit_that_caps_a_search():
    """The whole point: a count that could be truncated is the bug it fixes."""
    portal = StubPortal([row(project=f"P{i}", id=f"AK-{i:04d}") for i in range(41)])
    r = repo(portal)
    assert len((await r.search(ProjectFilters(limit=12), auth=AUTH)).items) == 12
    assert (await r.summarise(ProjectFilters(limit=12), auth=AUTH)).total == 41
