"""What the unbrand tools work with and what they leave on the record."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from .pdf import BBox


class ToolRejected(ValueError):
    """A tool refused the call. The reason goes back to the model as the tool's
    error, so it can choose differently; nothing on the page has changed."""


class MarkPosition(StrEnum):
    """Fixed positions only (LOOP.md): the model picks one, never coordinates."""

    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_CENTRE = "bottom_centre"


ElementKind = Literal["image", "shapes", "coloured shapes"]


class ElementRef(BaseModel):
    """Something drawn on a page that can be removed whole: one placement of an
    image, or a group of vector shapes close together (a logo, a monogram).
    Found by code so a model never has to say where it is, only which it is."""

    kind: ElementKind
    bbox: BBox


class Removal(BaseModel):
    """One thing taken out, for the approver. `page` is source numbering."""

    tool: str
    page: int | None = None
    detail: str
    area: BBox | None = None  # points; what an area action covered, so damage outside it shows


Box = tuple[int, int, int, int]  # x0, y0, x1, y1 on a 0-1000 grid over the page


class Element(BaseModel):
    """An element as a model sees it: the number drawn on the render, and where."""

    id: int
    kind: ElementKind
    box: Box


class Rendered(BaseModel):
    """What render_page hands the model: the picture with each element's number
    drawn on it, and the same elements as a list."""

    page: int
    jpeg: bytes
    elements: list[Element]


class TermsResult(BaseModel):
    """What redact_terms did: matches per term per page, and the terms it could
    not find in the source's text layer. An absent term does not stop the
    others: in a real run one wrong variant ("ARISTA’s") cancelled every name."""

    counts: dict[str, dict[int, int]]
    absent: list[str]


class Finished(BaseModel):
    pdf: bytes
    removals: list[Removal]
    dropped_pages: list[int]  # source numbering, as verify() wants it
