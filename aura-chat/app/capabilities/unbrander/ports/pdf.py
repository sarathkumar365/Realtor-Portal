from typing import Protocol

from ..domain import BBox, DrawnElement, MarkPosition, PdfFacts, Word


class OcrUnavailable(RuntimeError):
    """OCR was asked for and cannot run. Raised, never answered with empty text:
    a verify that silently skipped OCR would pass white-on-teal branding."""


class PdfInspector(Protocol):
    """Reads a PDF into plain facts.

    A port so verify() stays pure and is tested without PDFs.
    """

    def inspect(self, pdf: bytes, *, ocr: bool) -> PdfFacts: ...


class EditSession(Protocol):
    """One PDF open for editing. Mechanics only: every judgement (what may be
    removed, how much, how often) is in tools.py.

    Pages are 1-based source numbers for the whole session. Dropping a page and
    adding the mark wait for save(), so a number never shifts under the model
    and no later redaction can remove the mark.
    """

    page_count: int

    def page_size(self, page: int) -> tuple[float, float]: ...

    def words(self, page: int) -> list[Word]:
        """The page as it stands now, not as it was."""
        ...

    def elements(self, page: int) -> list[DrawnElement]:
        """Every image placement and every group of nearby vector shapes, any
        size. Which of them a model may pick is policy, in tools.py."""
        ...

    def groups_covered(self, page: int, box: BBox) -> list[DrawnElement]:
        """The shape groups, of any size, with at least one drawing wholly inside
        the box: the groups an area removal would take shapes from."""
        ...

    def shapes_cut(self, page: int, box: BBox) -> int:
        """How many drawn shapes the box overlaps without covering, leaving out a
        page-sized background: what an area removal would leave half drawn."""
        ...

    def render(self, page: int, dpi: int,
               marks: list[tuple[int, BBox]] | None = None) -> bytes:
        """JPEG: a 24-page brochure is 38 MB as PNG, over OpenRouter's 30 MB
        image limit per request, and 7 MB as JPEG. Each mark is drawn on the
        picture as a box with its number; the PDF is not touched."""
        ...

    def redact_text(self, page: int, boxes: list[BBox]) -> None:
        """Removes the text in the boxes; line art and images stay."""
        ...

    def redact_area(self, page: int, box: BBox) -> list[Word]:
        """Removes the text in the box, the shapes wholly inside it and the
        images under it; returns the words that were in it. A shape the box only
        touches stays: a brand panel behind a logo is not the logo. Raises
        ToolRejected, before changing anything, when an image in the box cannot be
        removed without damaging another the box only partly covers."""
        ...

    def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
        """Adds the mark, drops pages, strips metadata, writes the file and
        closes the session."""
        ...

    def close(self) -> None:
        """Closes a session that was only looked at. Safe after save()."""
        ...


class PdfEditor(Protocol):
    """Opens a PDF for the unbrand tools. A port, next to PdfInspector, so the tools'
    guards are tested with a fake and pymupdf stays in one adapter."""

    def open(self, pdf: bytes) -> EditSession: ...
