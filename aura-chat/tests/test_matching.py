"""The filter rules. Pure domain logic, so every case is one assertion."""

from app.domain import Project, ProjectFilters, matches, sort_key


def p(**over) -> Project:
    base = dict(
        id="x", name="Reva", city="BRAMPTON", builder="Great Gulf",
        property_type="Townhome", categories=["townhome"], starting_price=899_900,
        min_bedrooms=3, deposit_pct=10.0,
    )
    base.update(over)
    return Project(**base)


def f(**over) -> ProjectFilters:
    return ProjectFilters(**over)


def test_an_unpriced_project_never_satisfies_a_price_filter():
    """It is unknown, not cheap. Letting it through is how an answer asserts
    something the sheet never said."""
    assert not matches(p(starting_price=None), f(max_price=1_000_000))
    assert not matches(p(starting_price=None), f(min_price=500_000))


def test_max_price_is_inclusive():
    assert matches(p(starting_price=1_000_000), f(max_price=1_000_000))
    assert not matches(p(starting_price=1_000_001), f(max_price=1_000_000))


def test_min_price_tests_the_top_of_a_range():
    """A project selling from $800K to $1.4M does satisfy 'at least $1M'."""
    assert matches(p(starting_price=800_000, max_price=1_400_000), f(min_price=1_000_000))


def test_unavailable_projects_are_hidden_from_search_by_default():
    assert not matches(p(is_available=False), f())
    assert matches(p(is_available=False), f(include_unavailable=True))


def test_city_is_matched_exactly_not_by_substring():
    assert matches(p(city="BRAMPTON"), f(city="brampton"))
    assert not matches(p(city="BRAMPTON"), f(city="BRAMP"))


def test_categories_match_on_any_overlap():
    assert matches(p(categories=["detached", "semi"]), f(categories=["semi"]))
    assert not matches(p(categories=["condo"]), f(categories=["detached"]))


def test_min_bedrooms_uses_the_smallest_offered():
    assert matches(p(min_bedrooms=3), f(min_bedrooms=3))
    assert not matches(p(min_bedrooms=2), f(min_bedrooms=3))
    assert not matches(p(min_bedrooms=None), f(min_bedrooms=3))


def test_max_deposit_filter():
    assert matches(p(deposit_pct=10.0), f(max_deposit_pct=10.0))
    assert not matches(p(deposit_pct=15.0), f(max_deposit_pct=10.0))
    assert not matches(p(deposit_pct=None), f(max_deposit_pct=10.0))


def test_free_text_searches_name_builder_and_address():
    assert matches(p(), f(query="great gulf"))
    assert matches(p(address="12 Main St"), f(query="main st"))
    assert not matches(p(), f(query="mattamy"))


def test_focus_leads_and_unpriced_projects_sort_last():
    rows = [p(name="B"), p(name="A", starting_price=None), p(name="C", is_focus=True)]
    rows.sort(key=sort_key)
    assert [x.name for x in rows] == ["C", "B", "A"]


def test_focus_only_true_keeps_only_focus_projects():
    assert matches(p(is_focus=True), f(focus_only=True))
    assert not matches(p(is_focus=False), f(focus_only=True))


def test_focus_only_false_excludes_them():
    assert matches(p(is_focus=False), f(focus_only=False))
    assert not matches(p(is_focus=True), f(focus_only=False))


def test_unset_means_the_caller_did_not_ask():
    """None must not quietly become 'only the ones that are not focus' -- the
    reason the check is `is True` / `is False` and not truthiness."""
    assert matches(p(is_focus=True), f())
    assert matches(p(is_focus=False), f())


def test_a_category_matches_whatever_case_it_arrives_in():
    """The portal emits lowercase (catsFromType_ in Core.js) and the model sends
    whatever it likes -- currently "Townhome". An exact set intersection made
    that silence: search_projects ran, matched nothing, and Aura said it could
    not confirm any townhomes in a city that has twenty-one projects."""
    from app.domain import ProjectFilters
    from app.domain.matching import matches

    town = p(categories=["townhome"])
    for asked in ("townhome", "Townhome", "TOWNHOME", " Townhome "):
        assert matches(town, ProjectFilters(categories=[asked])), asked
    assert not matches(town, ProjectFilters(categories=["Condo"]))


def test_blank_categories_are_dropped_rather_than_matching_nothing():
    from app.domain import ProjectFilters

    assert ProjectFilters(categories=["", "  ", "Townhome"]).categories == ["townhome"]
