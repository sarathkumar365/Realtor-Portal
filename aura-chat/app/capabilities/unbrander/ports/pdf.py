from typing import Protocol

from ..domain import PdfFacts


class OcrUnavailable(RuntimeError):
    """OCR was asked for and cannot run. Raised, never answered with empty text:
    a verify that silently skipped OCR would pass white-on-teal branding."""


class PdfInspector(Protocol):
    """Reads a PDF into plain facts.

    A port so verify() stays pure and is tested without PDFs; the M2 tools
    will read through the same adapter.
    """

    def inspect(self, pdf: bytes, *, ocr: bool) -> PdfFacts: ...
