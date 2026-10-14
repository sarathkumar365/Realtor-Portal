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


class DrawnElement(BaseModel):
    """Something drawn on a page that can be removed whole: one placement of an
    image, or a group of vector shapes close together (a logo, a monogram).
    Found by code so a model never has to say where it is, only which it is.
    `bbox` is in points."""

    kind: ElementKind
    bbox: BBox


class Removal(BaseModel):
    """One thing taken out, for the approver. `page` is source numbering."""

    tool: str
    page: int | None = None
    detail: str
    area: BBox | None = None  # points; what an area action covered, so damage outside it shows


GridBox = tuple[int, int, int, int]  # x0, y0, x1, y1 on a 0-1000 grid over the page


def to_box_2d(box: GridBox) -> list[int]:
    """[ymin, xmin, ymax, xmax]: the order Gemini answers boxes in, so the order
    of every box a model is shown, in a list or in a refusal."""
    x0, y0, x1, y1 = box
    return [y0, x0, y1, x1]


def from_box_2d(box_2d: list[int]) -> GridBox:
    ymin, xmin, ymax, xmax = box_2d
    return (xmin, ymin, xmax, ymax)


class NumberedElement(BaseModel):
    """An element as a model sees it: the number drawn on the render, and where."""

    id: int
    kind: ElementKind
    box: GridBox


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
