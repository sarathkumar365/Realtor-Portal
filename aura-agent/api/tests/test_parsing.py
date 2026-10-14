"""The messiest input in the system: what a person typed into a cell.

Every case here is a real shape a price, deposit or date can arrive in. The
rule under test throughout: never guess. An ambiguous value returns None and the
project drops out of a numeric filter, because a missing answer is recoverable
and a confident wrong one is not.
"""

from datetime import date

import pytest

from app.adapters.parsing import (
    parse_date,
    parse_min_bedrooms,
    parse_money,
    parse_percent,
    parse_price_range,
    slugify,
)


@pytest.mark.parametrize(
    "raw,want",
    [
        ("899900", 899_900),
        ("$899,900", 899_900),
        ("From $899,900", 899_900),
        ("$899,900 + HST", 899_900),
        ("899K", 899_000),
        ("$1.2M", 1_200_000),
        ("1.2m", 1_200_000),
        ("  $1,249,000  ", 1_249_000),
        ("Starting at $749,990", 749_990),
    ],
)
def test_prices_people_actually_type(raw, want):
    assert parse_money(raw) == want


def test_a_range_yields_its_low_end():
    """A project selling from $899K should match 'under $1M'."""
    assert parse_money("$899,900 - $1,200,000") == 899_900


@pytest.mark.parametrize("raw", ["", "   ", "-", "TBD", "TBA", "N/A", "Call", "Coming Soon", None])
def test_unfilled_cells_are_not_zero(raw):
    assert parse_money(raw) is None


def test_a_bare_small_number_is_refused_rather_than_guessed():
    """'1.2' is somebody meaning millions, but guessing which is the invention
    the no-fabrication rule exists to stop."""
    assert parse_money("1.2") is None
    assert parse_money("999") is None


def test_price_range_in_one_column():
    assert parse_price_range("$899,900 - $1,200,000") == (899_900, 1_200_000)
    assert parse_price_range("$899,900") == (899_900, None)
    assert parse_price_range("TBD") == (None, None)


@pytest.mark.parametrize("raw,want", [("10%", 10.0), ("10", 10.0), ("5.5%", 5.5), ("20 %", 20.0)])
def test_deposit_percentages(raw, want):
    assert parse_percent(raw) == want


def test_a_percent_formatted_cell_shown_as_a_fraction():
    """0.1 is a spreadsheet rendering 10%. Read literally it would put every
    project under a 'max 10% deposit' filter."""
    assert parse_percent("0.1") == 10.0


@pytest.mark.parametrize("raw", ["", "TBD", "see schedule", "-"])
def test_unparseable_deposits_are_none(raw):
    assert parse_percent(raw) is None


def test_a_percentage_over_100_is_refused():
    assert parse_percent("150%") is None


@pytest.mark.parametrize("raw,want", [("3", 3), ("3-4", 3), ("3, 4, 5", 3), ("4 Beds", 4), ("2-3 BR", 2)])
def test_minimum_bedrooms(raw, want):
    """'at least 3 bedrooms' has to test the smallest count a project offers."""
    assert parse_min_bedrooms(raw) == want


@pytest.mark.parametrize("raw", ["", "TBD", "Various", "-"])
def test_unparseable_bedrooms_are_none(raw):
    assert parse_min_bedrooms(raw) is None


def test_iso_dates_are_read_exactly():
    assert parse_date("2026-08-24") == date(2026, 8, 24)


@pytest.mark.parametrize("raw,want", [("Aug 24, 2026", date(2026, 8, 24)), ("24 Aug 2026", date(2026, 8, 24))])
def test_written_dates(raw, want):
    assert parse_date(raw) == want


def test_ambiguous_slash_dates_read_month_first():
    """The sheet is typed month-first. 12/04/2026 is December 4, not April 12."""
    assert parse_date("12/04/2026") == date(2026, 12, 4)


def test_unambiguous_day_first_dates_still_parse():
    """25/12/2026 cannot be month-first, so day-first is provable."""
    assert parse_date("25/12/2026") == date(2026, 12, 25)


def test_unparseable_dates_are_none():
    assert parse_date("last week") is None
    assert parse_date("") is None
    # September has 30 days; a coin flip must not turn a typo into a date.
    assert parse_date("09/31/2025") is None


def test_slug_is_stable_for_the_same_project():
    a = slugify("BRAMPTON", "Reva Westfield")
    b = slugify("brampton", "  Reva  Westfield ")
    assert a == b == "brampton:reva-westfield"


def test_slug_changes_when_a_project_is_renamed():
    """The documented cost of shipping deep links before PROJECT ID is filled."""
    assert slugify("BRAMPTON", "Reva Westfield") != slugify("BRAMPTON", "Reva Westfield II")


@pytest.mark.parametrize("raw,want", [("1%", 1.0), ("0.5%", 0.5), ("1 %", 1.0)])
def test_a_percent_sign_means_the_value_is_already_a_percentage(raw, want):
    """A 1% deposit read as 100% tells a realtor the buyer pays the whole price
    up front, and drops the project from every 'max 10% deposit' search."""
    assert parse_percent(raw) == want


def test_the_fraction_correction_still_applies_without_a_percent_sign():
    assert parse_percent("0.1") == 10.0
    assert parse_percent("1") == 100.0


def test_is_blank_separates_unfilled_from_unreadable():
    """They both parse to None and mean opposite things about data health."""
    from app.adapters.parsing import is_blank

    assert is_blank("TBD") and is_blank("") and is_blank("N/A")
    assert not is_blank("somewhere around a million")
