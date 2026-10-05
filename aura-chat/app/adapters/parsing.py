"""Turning what a realtor typed into a sheet cell into something comparable.

These are the messiest functions in the service and the ones most likely to
need editing, so they live together, are pure, and are covered case by case in
tests/test_parsing.py. When a value comes back wrong, this is the file.

The guiding rule: **never guess a number.** "under $1M" answered from a
misparsed cell is the exact failure AUR-33 exists to prevent, so anything
ambiguous returns None and the project simply does not match a price filter.
A missing answer is recoverable; a confident wrong one is not.
"""

import re
from datetime import date, datetime

# "1.2M", "899K" -- suffixes realtors actually type.
_MULTIPLIER = {"K": 1_000, "M": 1_000_000}

# A number with optional thousands separators and decimals, plus an optional
# K/M suffix. Deliberately not anchored: prices arrive with prefixes ("From
# $899,900") and suffixes ("$899,900 + HST") we do not care about.
_NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm])?")

# Values that mean "nobody has filled this in", not "zero".
_BLANK = {"", "-", "--", "n/a", "na", "tbd", "tba", "coming soon", "call", "ask", "?"}


def is_blank(raw: object) -> bool:
    """Does this cell mean "nobody has filled this in" rather than a value?

    Public because callers need to tell an unfilled cell apart from one the
    parser could not read: they look identical (both parse to None) and mean
    opposite things about the data's health.
    """
    return str(raw or "").strip().lower() in _BLANK


_is_blank = is_blank  # the module's own call sites


def parse_money(raw: object) -> int | None:
    """A price cell to whole dollars.

    Handles: 899900 | $899,900 | From $899,900 | $1.2M | 899K |
             $899,900 - $1,200,000 (takes the low end) | blanks and TBD.

    A range yields its LOW end, because a range is what a project starts from
    and "under $1M" should match a project selling from $899K.
    """
    if _is_blank(raw):
        return None
    text = str(raw).strip()
    match = _NUMBER.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (match.group(2) or "").upper()
    if suffix:
        value *= _MULTIPLIER[suffix]
    # A bare "1.2" with no suffix is somebody meaning millions, but guessing
    # which is exactly the invention we refuse to do.
    if value < 1000:
        return None
    return int(round(value))


def parse_price_range(raw: object) -> tuple[int | None, int | None]:
    """Low and high from one cell, for tabs that carry a range in a single
    column (ONTARIO's PRICE RANGE) rather than two."""
    if _is_blank(raw):
        return None, None
    found = [parse_money(m.group(0)) for m in _NUMBER.finditer(str(raw))]
    found = [v for v in found if v is not None]
    if not found:
        return None, None
    if len(found) == 1:
        return found[0], None
    return min(found), max(found)


def parse_percent(raw: object) -> float | None:
    """A deposit cell to a percentage number: 10% -> 10.0, 0.1 -> 10.0, 1% -> 1.0.

    A bare value at or below 1 is a spreadsheet displaying a percent-formatted
    cell as a fraction; reading 0.1 as 0.1% would put every project under a
    "max 10% deposit" filter. But a value written WITH a percent sign already
    says what it is, so "1%" is one percent and must not be multiplied -- a
    100% deposit tells a realtor the buyer pays the whole price up front.
    """
    if _is_blank(raw):
        return None
    text = str(raw)
    match = _NUMBER.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    if value <= 1 and "%" not in text:
        value *= 100
    if not 0 < value <= 100:
        return None
    return round(value, 2)


def parse_min_bedrooms(raw: object) -> int | None:
    """The smallest bedroom count a project offers.

    "3-4" and "3, 4, 5" both mean a 3-bedroom is available, which is what
    "at least 3 bedrooms" has to test against.
    """
    if _is_blank(raw):
        return None
    numbers = [int(n) for n in re.findall(r"\d+", str(raw))]
    numbers = [n for n in numbers if 0 < n <= 12]
    return min(numbers) if numbers else None


_DATE_FORMATS = (
    "%Y-%m-%d",  # ISO, the format we asked for
    "%m/%d/%Y",  # the sheet's convention
    "%d/%m/%Y",  # only reachable when day > 12 -- unambiguously day-first
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%B %d, %Y",
)


def parse_date(raw: object) -> date | None:
    """A last-updated cell to a date.

    03/04/2026 is two different dates depending on who typed it, and the sheet
    is typed month-first -- so month-first is tried first and always wins the
    ambiguous case. The day-first formats after it can only match a value
    month-first cannot parse (first number 13-31), which is exactly the case
    where day-first is provable. recent() sorts on this value, so getting the
    order wrong puts stale projects at the top of "what changed this week".
    """
    if _is_blank(raw):
        return None
    text = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(city: object, name: object) -> str:
    """A stable-enough identifier for a project that has no PROJECT ID yet.

    Sudhanshu is filling the real column now; until then this keeps deep links
    and comparison working. It is derived from the name, so **renaming a project
    changes its id** and any link minted beforehand stops resolving. That is the
    trade for having the feature before the data. A real PROJECT ID always wins
    when one is present.
    """
    parts = [_SLUG_STRIP.sub("-", str(v or "").strip().lower()).strip("-") for v in (city, name)]
    return ":".join(p for p in parts if p)
