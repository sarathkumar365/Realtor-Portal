"""What a PDF contains, as plain facts.

The adapter extracts these once; everything that judges a PDF works on them. No
pymupdf type crosses this line, so verify() is tested on hand-built facts and
never needs a real PDF.
"""

from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]

# OCR modes. "light" isolates light ink: white text on a teal panel is invisible
# to the text layer and to normal OCR, and it is the leak that actually shipped.
OCR_MODES = ("normal", "inverted", "light")


class Word(BaseModel):
    text: str
    bbox: BBox


class Paint(BaseModel):
    """One entry of the page's paint log, in the order it is drawn.

    `kind` is "text", "image" or "path". `opaque` is only ever true for a path
    with a fully opaque fill: a translucent tint over a photo is design, an
    opaque box over text is a cover-up.
    """

    kind: str
    bbox: BBox
    opaque: bool = False


class Thumbnail(BaseModel):
    """The page rendered small in gray, one byte per pixel, row by row. The damage
    check compares two of these: counting shapes does not work, because a
    redaction rewrites the page and merges its drawing commands (2,137 paths
    became 620 on a Bright Side floor plan that looked the same)."""

    width: int
    height: int
    gray: bytes


class PageFacts(BaseModel):
    number: int  # 1-based, as a human reads it
    width: float
    height: float
    words: list[Word] = Field(default_factory=list)
    paint: list[Paint] = Field(default_factory=list)
    ocr: dict[str, str] = Field(default_factory=dict)  # mode -> text; empty when not run
    thumbnail: Thumbnail | None = None


class PdfFacts(BaseModel):
    pages: list[PageFacts]
    metadata: dict[str, str] = Field(default_factory=dict)  # title, author, ... non-empty only
    xmp: str = ""
    annotations: int = 0
    links: int = 0
    embedded_files: int = 0
    # Every object's definition (not stream bodies), plus layer names. Names of
    # things never drawn live here: Haiku left "SouthCal_DT 2001" behind in one.
    object_text: str = ""
