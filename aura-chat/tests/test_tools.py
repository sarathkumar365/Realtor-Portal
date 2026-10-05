"""The tools, against a fake repo. No network, no model, no sheet."""

import pytest

from app import tools
from app.adapters.projects_redacting import RedactingProjectRepo
from app.domain import ChatMode, Project, Role, Viewer
from tests.fakes import FakeProjectRepo

AUTH = "tok"


def p(name, **over) -> Project:
    base = dict(
        id=name.lower(), name=name, city="BRAMPTON", builder="Great Gulf",
        property_type="Townhome", categories=["townhome"], starting_price=899_900,
        min_bedrooms=3, deposit_pct=10.0, is_available=True,
        builder_login="agent@builder", commission="4%",
    )
    base.update(over)
    return Project(**base)


@pytest.fixture
def repo():
    return FakeProjectRepo(
        [
            p("Reva", starting_price=899_900),
            p("Kai", starting_price=1_250_000, categories=["detached"]),
            p("Solera", starting_price=None),
            p("Gone", is_available=False),
        ]
    )


async def test_search_returns_domain_objects(repo):
    out = (await tools.search_projects(repo, auth=AUTH, city="BRAMPTON")).items
    assert out and all(isinstance(x, Project) for x in out)


async def test_a_redacting_repo_is_what_makes_a_tool_safe(repo):
    """Tools have no redaction step. They are handed a repo that cannot return
    an unredacted record, so a tool added in a hurry cannot forget one."""
    client_view = RedactingProjectRepo(repo, Viewer(role=Role.REALTOR, mode=ChatMode.CLIENT))
    out = (await tools.search_projects(client_view, auth=AUTH)).items
    assert out and all(x.commission == "" for x in out)


async def test_the_same_tool_over_a_realtor_view_keeps_the_field(repo):
    realtor_view = RedactingProjectRepo(repo, Viewer(role=Role.REALTOR, mode=ChatMode.REALTOR))
    out = (await tools.search_projects(realtor_view, auth=AUTH)).items
    assert any(x.commission for x in out)


async def test_results_are_capped(repo):
    """One question must never drag the whole sheet into a prompt (AUR-17)."""
    big = FakeProjectRepo([p(f"P{i}") for i in range(100)])
    out = (await tools.search_projects(big, auth=AUTH, limit=999)).items
    assert len(out) <= tools.MAX_RESULTS


async def test_compare_is_capped_and_skips_unknown_ids(repo):
    out = await tools.compare_projects(repo, ["reva", "kai", "nope"], auth=AUTH)
    assert [x.name for x in out] == ["Reva", "Kai"]


async def test_get_project_returns_none_for_an_unknown_id(repo):
    assert await tools.get_project(repo, "nope", auth=AUTH) is None


async def test_get_project_is_redacted_by_the_repo_it_is_given(repo):
    client_view = RedactingProjectRepo(repo, Viewer(role=Role.REALTOR, mode=ChatMode.CLIENT))
    out = await tools.get_project(client_view, "reva", auth=AUTH)
    assert out is not None and out.commission == ""


async def test_search_can_ask_for_focus_projects():
    """30 projects carry the brokerage's own priority flag. It was sortable
    from the start but not askable, so Aura answered "I can't search for focus
    projects" about a signal every other surface exposes."""
    mixed = FakeProjectRepo([p("Pushed", is_focus=True), p("Ordinary", is_focus=False)])
    out = (await tools.search_projects(mixed, auth=AUTH, focus_only=True)).items
    assert [x.name for x in out] == ["Pushed"]


async def test_search_without_focus_returns_both():
    mixed = FakeProjectRepo([p("Pushed", is_focus=True), p("Ordinary", is_focus=False)])
    assert len((await tools.search_projects(mixed, auth=AUTH)).items) == 2


async def test_a_capped_search_reports_how_many_actually_matched():
    """The page is 12; the answer must be able to say 41.

    Without this the model reads 12 rows and says "we have 12 townhomes in
    Brampton" -- a statement about the page, phrased as a statement about the
    brokerage.
    """
    many = FakeProjectRepo([
        Project(id=f"p{i}", name=f"P{i}", city="BRAMPTON") for i in range(41)
    ])
    page = await tools.search_projects(many, auth=AUTH, city="BRAMPTON")
    assert len(page.items) == tools.MAX_RESULTS
    assert page.total == 41
    assert page.truncated is True


async def test_an_uncapped_search_is_not_reported_as_truncated():
    few = FakeProjectRepo([Project(id="p1", name="P1", city="BRAMPTON")])
    page = await tools.search_projects(few, auth=AUTH, city="BRAMPTON")
    assert page.total == 1 and page.truncated is False


async def test_a_summary_counts_every_match_not_just_a_page():
    """The bug this exists for: 41 matched, 12 were shown, and the model
    answered "we have 12" and "we are in 9 cities" from the 12."""
    rows = [
        Project(id=f"p{i}", name=f"P{i}", city="BRAMPTON" if i % 2 else "CALEDON")
        for i in range(41)
    ]
    s = await tools.inventory_summary(FakeProjectRepo(rows), auth=AUTH)
    assert s.total == 41
    assert sum(t.count for t in s.cities) == 41
    assert {t.label for t in s.cities} == {"BRAMPTON", "CALEDON"}
    assert len(s.names) == 41


async def test_the_cheapest_is_the_cheapest_of_all_of_them():
    """Not of the page. The one on the last row is the point."""
    rows = [Project(id=f"p{i}", name=f"P{i}", city="X", starting_price=900_000 - i)
            for i in range(41)]
    s = await tools.inventory_summary(FakeProjectRepo(rows), auth=AUTH)
    assert s.cheapest.starting_price == 900_000 - 40
    assert s.dearest.starting_price == 900_000
    assert s.without_price == 0


async def test_projects_with_no_price_are_counted_not_ignored():
    """"Cheapest" over a set where most rows have no price is a half-truth
    unless the count of the excluded half comes with it."""
    rows = [
        Project(id="a", name="A", city="X", starting_price=500_000),
        Project(id="b", name="B", city="X"),
        Project(id="c", name="C", city="X"),
    ]
    s = await tools.inventory_summary(FakeProjectRepo(rows), auth=AUTH)
    assert s.total == 3 and s.without_price == 2
    assert s.cheapest.id == "a"


async def test_an_empty_summary_names_nothing_rather_than_guessing():
    s = await tools.inventory_summary(FakeProjectRepo([]), auth=AUTH)
    assert s.total == 0 and s.cheapest is None and s.dearest is None and s.names == []
