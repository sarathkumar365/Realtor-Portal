"""The project record, as the business means it -- not as a sheet stores it.

Every adapter maps its own storage into this shape, so nothing above the
adapter layer ever learns a tab name, a row number or a column header.
"""

from datetime import date

from pydantic import BaseModel, Field, field_validator

# Every field that is hidden from somebody. What is hidden from WHOM lives in
# viewer.py; this set exists so a redaction can be checked for completeness --
# adding a confidential field to Project means adding it here and to the right
# audience list in the same commit.
CONFIDENTIAL_FIELDS = frozenset(
    {
        "builder_login",
        "builder_office",
        "builder_contact",
        "fub_template",
        "commission",
        "internal_notes",
        "broker_url",
        "drive_url",
        "status",
    }
)


class Project(BaseModel):
    """One project, from any source."""

    # identity
    id: str | None = None  # PROJECT ID once populated; None until then
    name: str
    city: str
    builder: str = ""

    # classification
    property_type: str = ""
    address: str = ""
    categories: list[str] = Field(default_factory=list)  # detached/semi/townhome/condo
    status: str = ""
    is_focus: bool = False
    # "Not Available" in the sheet. Carried rather than dropped: search hides
    # these, but "what happened to X?" still has to find one.
    is_available: bool = True

    # commercial
    starting_price: int | None = None
    max_price: int | None = None
    bedrooms: str = ""
    min_bedrooms: int | None = None  # smallest count offered, for "3+ bedrooms"
    deposit_pct: float | None = None
    deposit_schedule: str = ""
    incentives: str = ""
    occupancy: str = ""

    # provenance (AUR-32)
    last_updated: date | None = None
    source_url: str = ""

    # links
    website_url: str = ""          # the builder's public site; safe for a buyer
    # drive_url and broker_url are confidential -- see CONFIDENTIAL_FIELDS
    drive_url: str = ""
    broker_url: str = ""

    # confidential -- see CONFIDENTIAL_FIELDS
    builder_login: str = ""
    builder_office: str = ""
    builder_contact: str = ""
    fub_template: str = ""
    commission: str = ""
    internal_notes: str = ""

    def for_viewer(self, viewer) -> "Project":
        """A copy carrying only what this viewer may see.

        Returns a new object rather than mutating: the same Project may be
        rendered to the realtor and, a moment later, to a buyer.

        The viewer is typed loosely to keep this module free of an import
        cycle; anything exposing `hidden_fields` will do.
        """
        hidden = viewer.hidden_fields
        if not hidden:
            return self
        return self.model_copy(update={f: "" for f in hidden})

    @property
    def is_ai_ready(self) -> bool:
        """AUR-31: the minimum a project needs before Aura may answer about it.

        A project missing these is not hidden -- it is simply never presented as
        a priced, linkable result.
        """
        return bool(self.id and self.name and self.city and self.property_type)


class ProjectFilters(BaseModel):
    """A search expressed as intent, never as storage mechanics.

    This is what makes the ProjectRepo port swappable: the sheet adapter
    filters in Python, a future SQL adapter turns the same object into a WHERE
    clause, and no caller has to know which.
    """

    query: str = ""  # free text over name/builder
    city: str = ""
    builder: str = ""
    categories: list[str] = Field(default_factory=list)

    @field_validator("categories", mode="after")
    @classmethod
    def _fold_categories(cls, v: list[str]) -> list[str]:
        """Categories are compared as an exact set, so casing decides the answer.

        The portal emits them lowercase (catsFromType_ in Core.js) and the model
        supplies whatever it likes -- it currently sends "Townhome". Folded here
        rather than in `matches` so a future SQL adapter gets it too.
        """
        return [c.strip().lower() for c in v if c and c.strip()]
    min_price: int | None = None
    max_price: int | None = None
    min_bedrooms: int | None = None
    max_deposit_pct: float | None = None
    status: str = ""
    occupancy: str = ""
    # The brokerage's own priority signal, carried on the STATUS column. It was
    # sortable from the start but not askable, so "what should I be pushing?" --
    # the question an assistant most obviously exists to answer -- had no way
    # through. None means "do not care", which is not the same as False.
    focus_only: bool | None = None
    include_unavailable: bool = False
    limit: int = 20


class SearchPage(BaseModel):
    """A page of results that remembers how many there were.

    The cap exists so a realtor gets an answer rather than a catalogue, but
    `items` alone is indistinguishable from "this is everything". The model was
    reading 12 rows and answering "we have projects in 9 cities" -- a statement
    about the page, phrased as a statement about the brokerage.

    `total` is what matched before the cap, so the answer can say "12 of 41".
    It is not a substitute for `inventory_summary`: knowing 41 matched still
    does not tell you the cheapest of the 41.
    """

    items: list[Project] = Field(default_factory=list)
    total: int = 0

    @property
    def truncated(self) -> bool:
        return self.total > len(self.items)


# Names are capped because the answer is read on a phone. The cap is generous
# enough that it almost never bites, and `names_truncated` says so when it does
# -- an unflagged cut here would recreate the exact bug this model exists to
# fix, one layer down.
MAX_SUMMARY_NAMES = 60


class Tally(BaseModel):
    """One label and how many projects carry it."""

    label: str
    count: int


class InventorySummary(BaseModel):
    """What a whole matching set looks like, without returning the set.

    A capped search cannot answer "how many", "which cities", or "the cheapest"
    -- those are claims about every match, and a page of 12 cannot support one.
    This is computed over all of them and returns counts and names, never
    project records, so a counting question stops producing a truncated list of
    cards that reads as though it were the whole inventory.

    It aggregates only fields no audience is denied -- name, city, builder,
    price -- so it is not a way around redaction. `test_summary_exposes_no_
    hidden_field` holds that line.
    """

    total: int = 0
    names: list[str] = Field(default_factory=list)
    names_truncated: bool = False
    cities: list[Tally] = Field(default_factory=list)
    builders: list[Tally] = Field(default_factory=list)
    cheapest: Project | None = None
    dearest: Project | None = None
    # Projects that matched but carry no readable price. Without it, "cheapest"
    # silently means "cheapest of those with a price", which on this sheet is
    # 29 of 163 -- and the realtor has no way to see the difference.
    without_price: int = 0
