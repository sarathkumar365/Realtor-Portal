"""ProjectRepo backed by the portal's Apps Script API.

This is the only file in the service that knows a sheet column exists. Header
names, row numbers and "$899,900" all stop at `_to_project`; everything above
sees `Project`. That containment is what makes moving to a database a matter of
writing a sibling adapter rather than touching tools, prompts or the API.
"""

import time
from datetime import date

from app.domain import (
    MAX_SUMMARY_NAMES,
    InventorySummary,
    Project,
    ProjectFilters,
    SearchPage,
    Tally,
    matches,
    sort_key,
)

from .parsing import (
    is_blank,
    parse_date,
    parse_min_bedrooms,
    parse_money,
    parse_percent,
    parse_price_range,
    slugify,
)
from .portal_client import PortalClient, PortalError

# Tabs that are not cities. ONTARIO is a roll-up: 87 of the sheet's 250 rows,
# 63 of them second copies of a project that already has a row on its real city
# tab -- and the copies disagree. Caledon Club is 2027/2028 and a focus project
# on the CALEDON tab, 2026 and not a focus project on this one. Nothing in the
# payload marks the pair as the same building, so both reach the model as
# separate projects and either date can be quoted as fact. The rest of the tab
# is aliases ("Duo" for DUO Condos, with a staler occupancy) and roll-up
# entries that are not projects at all ("Mattamy All Projects").
#
# Dropped here rather than in Ai.js so the sheet keeps whatever use it has for
# the tab, and so undoing this is a one-line revert instead of a deployment.
ROLLUP_CITIES = frozenset({"ONTARIO"})


def _tally(values) -> list[Tally]:
    """Counts per label, commonest first, blanks dropped.

    A blank builder is a column nobody filled, not a builder named "". Counting
    it would put an unnamed bucket at the top of a list the realtor reads as
    "who we work with".
    """
    counts: dict[str, int] = {}
    for v in values:
        label = str(v or "").strip()
        if label:
            counts[label] = counts.get(label, 0) + 1
    return [
        Tally(label=k, count=n)
        for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


class ExecApiProjectRepo:
    # The portal rebuilds this index at most every few hours and Sudhanshu edits
    # the sheets live during the sprint, so the window is a compromise between a
    # stale demo and portal runtime -- a budget shared with the realtors' own
    # app. Five minutes is roughly one fetch per conversation rather than one
    # per question.
    TTL_S = 300.0
    # A cache-busting rebuild walks all ~38 city tabs. The ordinary read budget
    # is sized for a cached hit and cuts this off part-way, so the diagnostic
    # path gets its own.
    REFRESH_TIMEOUT_S = 240.0

    def __init__(self, portal: PortalClient, *, ttl_s: float | None = None) -> None:
        self._portal = portal
        self._ttl = self.TTL_S if ttl_s is None else ttl_s
        self._cached: list[Project] | None = None
        self._fetched_at = 0.0
        # Counted, not logged: a spike in unparsed prices means Sudhanshu has
        # started writing them a new way, and /doctor should say so before a
        # realtor finds out by getting a wrong answer.
        self.unparsed_prices = 0
        self.total_rows = 0
        # Reported by /doctor. A whole tab vanishing from the index is the kind
        # of thing a future reader deletes as dead code unless the number is
        # visible somewhere.
        self.skipped_rollup_rows = 0
        # A date after today is a typo, and recent() excludes it rather than
        # ranking it first. Counted so /doctor names the problem instead of the
        # answer just quietly missing a project.
        self.future_dated = 0

    # -- port ----------------------------------------------------------------

    async def search(self, filters: ProjectFilters, *, auth: str) -> SearchPage:
        rows = await self._index(auth)
        # Every row is tested and every match ranked -- the cap is on what the
        # caller carries away, not on what was considered.
        hits = [p for p in rows if matches(p, filters)]
        hits.sort(key=sort_key)
        return SearchPage(items=hits[: filters.limit], total=len(hits))

    async def summarise(self, filters: ProjectFilters, *, auth: str) -> InventorySummary:
        rows = await self._index(auth)
        # The same `matches` the search uses, so a summary can never describe a
        # different set from the one the realtor would get by searching.
        hits = [p for p in rows if matches(p, filters)]
        priced = [p for p in hits if p.starting_price is not None]
        names = sorted(p.name for p in hits)
        return InventorySummary(
            total=len(hits),
            names=names[:MAX_SUMMARY_NAMES],
            names_truncated=len(names) > MAX_SUMMARY_NAMES,
            cities=_tally(p.city for p in hits),
            builders=_tally(p.builder for p in hits),
            cheapest=min(priced, key=lambda p: p.starting_price, default=None),
            dearest=max(priced, key=lambda p: p.starting_price, default=None),
            without_price=len(hits) - len(priced),
        )

    async def get(self, project_id: str, *, auth: str) -> Project | None:
        rows = await self._index(auth)
        # Unavailable projects are reachable by id on purpose: search hides them,
        # but "what happened to X?" still needs an answer.
        # Exact match first: once PROJECT IDs are hand-filled, two rows could
        # differ only by case, and the casefolded fallback must not shadow the
        # id the caller actually typed.
        exact = next((p for p in rows if p.id == project_id), None)
        if exact is not None:
            return exact
        wanted = project_id.casefold()
        return next((p for p in rows if p.id.casefold() == wanted), None)

    async def recent(self, days: int, *, auth: str, limit: int = 20) -> list[Project]:
        rows = await self._index(auth)
        today = date.today()
        # A date after today is a typo, not a change -- without this bound the
        # descending sort would rank it first, every week, until it arrives.
        # Excluded at query time, not index time: a cached future date
        # legitimately becomes past.
        dated = [
            p
            for p in rows
            if p.last_updated is not None and p.is_available and p.last_updated <= today
        ]
        dated.sort(key=lambda p: p.last_updated, reverse=True)
        # Anchored to today, deliberately. Measuring from the newest row instead
        # would mean a sheet nobody has touched for six weeks still reports its
        # newest projects as "what changed this week" -- freshness the sheet
        # never claimed -- and would make an empty result impossible, so
        # "nothing changed recently" could never be answered.
        cutoff = today.toordinal() - days
        return [p for p in dated if p.last_updated.toordinal() >= cutoff][:limit]

    async def refresh(self, *, auth: str) -> int:
        """Force both caches -- ours and the portal's -- to rebuild.

        The portal rate-limits this to one rebuild per action per 30s and a full
        rebuild walks every city tab, so it is a diagnostic path, never
        something a question triggers.
        """
        self.invalidate()
        return len(await self._index(auth, fresh=True))

    async def healthy(self) -> bool:
        return await self._portal.healthy()

    # -- cache ---------------------------------------------------------------

    def invalidate(self) -> None:
        self._cached = None

    async def _index(self, auth: str, *, fresh: bool = False) -> list[Project]:
        """The whole project set, cached in this process.

        One payload rather than a filtered query per question: filtering happens
        in Python, so a busy conversation costs one portal fetch per window.

        Known limit: the cache is per process. If this ever runs on more than one
        worker, each keeps its own copy and the portal sees one fetch per worker
        per window. At this team's size we do not scale out; revisit if we do.

        ONE slot, shared by every caller, filled by whoever arrived first. Safe
        only because `aiindex` returns the same bytes to every signed-in
        realtor. If it ever varies by role or permission, this must be keyed on
        the same axis or removed -- an admin's payload would otherwise be served
        to every realtor behind them. See invariants.md #9.
        """
        now = time.monotonic()
        if not fresh and self._cached is not None and now - self._fetched_at < self._ttl:
            return self._cached
        data = await self._portal.call(
            "aiindex",
            auth=auth,
            **({"fresh": True, "timeout_s": self.REFRESH_TIMEOUT_S} if fresh else {}),
        )
        if data.get("ok") is False:
            raise PortalError(str(data.get("error") or "portal refused aiindex"))
        rows = data.get("rows") or []
        parsed, unparsed, rollup = [], 0, 0
        for raw in rows:
            if str(raw.get("city") or "").strip().upper() in ROLLUP_CITIES:
                rollup += 1
                continue
            project = self._to_project(raw)
            if project is None:
                continue
            # "TBD" and "Call" are correct data entry, and the parser returns
            # None for them by design. Counting those would bury the signal this
            # exists to give -- a real change in how prices are written -- under
            # noise from values already handled exactly as intended.
            if not is_blank(raw.get("price")) and project.starting_price is None:
                unparsed += 1
            parsed.append(project)
        self._cached = parsed
        self._fetched_at = now
        self.unparsed_prices = unparsed
        self.total_rows = len(parsed)
        self.skipped_rollup_rows = rollup
        today = date.today()
        self.future_dated = sum(
            1 for p in parsed if p.last_updated is not None and p.last_updated > today
        )
        return parsed

    # -- mapping: the containment boundary ------------------------------------

    @staticmethod
    def _to_project(raw: dict) -> Project | None:
        name = str(raw.get("project") or "").strip()
        city = str(raw.get("city") or "").strip()
        if not name or not city:
            return None
        if city.upper() in ROLLUP_CITIES:
            return None

        # Some tabs carry one PRICE RANGE column instead of two, so the price
        # cell is read as a range in every case. Asking parse_money first and
        # falling back only when it fails would never reach the fallback: its
        # regex is unanchored, so it happily returns the first number in
        # "$800,000 - $1,400,000" and the high end would be lost.
        low, span_high = parse_price_range(raw.get("price"))
        high = parse_money(raw.get("maxprice"))
        if high is None:
            high = span_high

        return Project(
            # A real PROJECT ID always wins; the slug is scaffolding until
            # Sudhanshu's column is filled, and changes if a project is renamed.
            id=str(raw.get("id") or "").strip() or slugify(city, name),
            name=name,
            city=city,
            builder=str(raw.get("builder") or "").strip(),
            property_type=str(raw.get("type") or "").strip(),
            address=str(raw.get("address") or "").strip(),
            categories=list(raw.get("cats") or []),
            status=str(raw.get("status") or "").strip(),
            is_focus=bool(raw.get("focus")),
            is_available=not bool(raw.get("hidden")),
            starting_price=low,
            max_price=high,
            bedrooms=str(raw.get("beds") or "").strip(),
            min_bedrooms=parse_min_bedrooms(raw.get("beds")),
            deposit_pct=parse_percent(raw.get("depositpct")),
            deposit_schedule=str(raw.get("depositsched") or "").strip(),
            incentives=str(raw.get("incentives") or "").strip(),
            occupancy=str(raw.get("occupancy") or "").strip(),
            last_updated=parse_date(raw.get("lastupdated")),
            source_url=str(raw.get("sourceurl") or "").strip(),
            website_url=str(raw.get("website_url") or "").strip(),
            drive_url=str(raw.get("drive_url") or "").strip(),
            broker_url=str(raw.get("broker_url") or "").strip(),
            builder_login=str(raw.get("login") or "").strip(),
            builder_office=str(raw.get("office") or "").strip(),
            builder_contact=str(raw.get("contact") or "").strip(),
            fub_template=str(raw.get("fub") or "").strip(),
        )
