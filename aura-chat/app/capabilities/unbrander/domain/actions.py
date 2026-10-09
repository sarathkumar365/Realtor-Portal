"""The unbrand step as data: the actions a model decides, what each did, and
what a model sees.

The plan a model returns is a list of tool calls with their inputs. Code applies
them through the Toolbox guards, so a round can be replayed from the source and
the approver reads every decision with its reason.
"""

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field

from .edit import GridBox, MarkPosition, NumberedElement
from .verify import HitList


class RedactTerms(BaseModel):
    tool: Literal["redact_terms"] = "redact_terms"
    terms: list[str]
    why: str


class RedactRect(BaseModel):
    tool: Literal["redact_rect"] = "redact_rect"
    page: int
    box: GridBox
    why: str


class RemoveElement(BaseModel):
    tool: Literal["remove_element"] = "remove_element"
    page: int
    element_id: int
    why: str


class DropPage(BaseModel):
    tool: Literal["drop_page"] = "drop_page"
    page: int
    why: str


class AddMark(BaseModel):
    tool: Literal["add_mark"] = "add_mark"
    position: MarkPosition
    why: str


Action = Annotated[RedactTerms | RedactRect | RemoveElement | DropPage | AddMark,
                   Field(discriminator="tool")]


class Outcome(BaseModel):
    """`ok=False`: a guard refused the action and `detail` says why. Otherwise
    `detail` is what the approver should know (collateral words, other pages)."""

    action: Action
    ok: bool
    detail: str = ""


PageKind = Literal["floor_plan", "elevation", "site_plan", "price_list", "feature_sheet",
                   "terms", "marketing"]
PAGE_KINDS: tuple[PageKind, ...] = get_args(PageKind)
# Page kinds a buyer needs. Everything else is the builder's marketing and is
# dropped: the skill's own output of the spike brochure kept the elevations and
# floor plans and nothing else (2026-10-08).
KEPT_KINDS = frozenset(kind for kind in PAGE_KINDS if kind != "marketing")
# The skill's mark positions: bottom right where a plan fills the page, bottom
# centre on text pages.
PLAN_KINDS = frozenset({"floor_plan", "site_plan", "elevation"})


class PageSort(BaseModel):
    page: int
    kind: PageKind
    keep: bool
    why: str


class Sorting(BaseModel):
    """The whole document read once: what each page is, which stay, and the
    exact strings to take out of the text on every page."""

    pages: list[PageSort]
    terms: list[str]


class PageView(BaseModel):
    """One page as a model sees it. `page` is always source numbering."""

    page: int
    jpeg: bytes
    text: str  # already wrapped as <document_text> data
    elements: list[NumberedElement]


class Brief(BaseModel):
    hits: HitList
    page_count: int
    instructions: str | None = None  # the operator's request; never overrides a guard


class Usage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # USD, as OpenRouter reports it; 0 when it does not
