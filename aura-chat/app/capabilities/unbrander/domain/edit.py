"""What the M2 tools work with and what they leave on the record."""

from enum import StrEnum

from pydantic import BaseModel

from .pdf import BBox


class ToolRejected(ValueError):
    """A tool refused the call. The reason goes back to the model as the tool's
    error, so it can choose differently; nothing on the page has changed."""


class MarkPosition(StrEnum):
    """Fixed positions only (LOOP.md): the model picks one, never coordinates."""

    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_CENTRE = "bottom_centre"


class ImageRef(BaseModel):
    id: int  # the image's xref: one image drawn on several pages has one id
    bbox: BBox
    pages: list[int]  # every page that draws it, 1-based


class Removal(BaseModel):
    """One thing taken out, for the approver. `page` is source numbering."""

    tool: str
    page: int | None = None
    detail: str


Box = tuple[int, int, int, int]  # x0, y0, x1, y1 on a 0-1000 grid over the page


class PageImage(BaseModel):
    id: int
    box: Box


class Rendered(BaseModel):
    """What render_page hands the model: the picture, and the images on it so
    delete_image has ids to name."""

    page: int
    png: bytes
    images: list[PageImage]


class Finished(BaseModel):
    pdf: bytes
    removals: list[Removal]
    dropped_pages: list[int]  # source numbering, as verify() wants it
