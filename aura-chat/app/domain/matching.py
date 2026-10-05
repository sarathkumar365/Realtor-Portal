"""Does this project satisfy this search? Pure, no I/O.

Lives in the domain rather than in an adapter because the answer is a business
question, not a storage one: a Postgres adapter would express the same rules as
a WHERE clause, and the two must agree.
"""

from .project import Project, ProjectFilters


def _text_of(p: Project) -> str:
    return " ".join((p.name, p.builder, p.city, p.property_type, p.address)).lower()


def matches(p: Project, f: ProjectFilters) -> bool:
    if not f.include_unavailable and not p.is_available:
        return False
    if f.city and p.city.upper() != f.city.upper():
        return False
    if f.builder and f.builder.lower() not in p.builder.lower():
        return False
    if f.categories and not set(f.categories) & {c.lower() for c in p.categories}:
        return False
    if f.status and f.status.lower() not in p.status.lower():
        return False
    # `is True` and `is False`, not truthiness: None means the caller did not
    # ask, and must not quietly become "only the ones that are not focus".
    if f.focus_only is True and not p.is_focus:
        return False
    if f.focus_only is False and p.is_focus:
        return False
    if f.occupancy and f.occupancy.lower() not in p.occupancy.lower():
        return False
    if f.query and f.query.lower() not in _text_of(p):
        return False

    # A project with no price is not "cheap enough" -- it is unknown. Letting an
    # unpriced project through a price filter is how an answer ends up asserting
    # something the sheet never said.
    if f.max_price is not None and (p.starting_price is None or p.starting_price > f.max_price):
        return False
    if f.min_price is not None:
        # Compare against the top of a range: a project selling from $800K to
        # $1.4M does satisfy "at least $1M".
        ceiling = p.max_price if p.max_price is not None else p.starting_price
        if ceiling is None or ceiling < f.min_price:
            return False
    if f.min_bedrooms is not None and (p.min_bedrooms is None or p.min_bedrooms < f.min_bedrooms):
        return False
    if f.max_deposit_pct is not None and (
        p.deposit_pct is None or p.deposit_pct > f.max_deposit_pct
    ):
        return False
    return True


def sort_key(p: Project) -> tuple:
    """Focus projects first, then cheapest known price, then name.

    Focus leads because it is the brokerage's own signal about what to sell;
    unpriced projects sort last rather than first, so a half-filled sheet does
    not push unknowns to the top of every answer.
    """
    return (
        0 if p.is_focus else 1,
        p.starting_price if p.starting_price is not None else float("inf"),
        p.name.lower(),
    )
