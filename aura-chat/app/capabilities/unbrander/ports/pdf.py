from typing import Protocol

from ..domain import BBox, ImageRef, MarkPosition, PdfFacts, Word


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

    def images(self, page: int) -> list[ImageRef]: ...

    def render(self, page: int, dpi: int) -> bytes:
        """PNG."""
        ...

    def redact_text(self, page: int, boxes: list[BBox]) -> None:
        """Removes the text in the boxes; line art and images stay."""
        ...

    def redact_area(self, page: int, box: BBox) -> list[Word]:
        """Removes everything in the box; returns the words that were in it."""
        ...

    def delete_image(self, page: int, image_id: int) -> None: ...

    def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
        """Adds the mark, drops pages, strips metadata, and writes the file."""
        ...


class PdfEditor(Protocol):
    """Opens a PDF for the M2 tools. A port, next to PdfInspector, so the tools'
    guards are tested with a fake and pymupdf stays in one adapter."""

    def open(self, pdf: bytes) -> EditSession: ...
