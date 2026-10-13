"""The door: an upload is refused here, with a fixed message, before any model
sees it or any job row is written (SECURITY.md, input guardrails).

Active content is refused, not stripped: stripping is a later change, and a
refusal costs nothing but a re-export from the builder's file.
"""

from .domain import Screening
from .ports import PdfInspector

PDF_MAGIC = b"%PDF-"


class UploadRejected(ValueError):
    def __init__(self, filename: str, reason: str, *, too_large: bool = False) -> None:
        super().__init__(f"{filename}: {reason}")
        self.too_large = too_large


def check_upload(filename: str, data: bytes, *, inspector: PdfInspector,
                 max_mb: int, max_pages: int) -> Screening:
    if len(data) > max_mb * 1024 * 1024:
        raise UploadRejected(filename, f"larger than {max_mb} MB", too_large=True)
    # By content, not by name: a renamed Word file must not reach the PDF tools.
    if not data.startswith(PDF_MAGIC):
        raise UploadRejected(filename, "not a PDF")
    screening = inspector.screen(data)
    if not screening.readable:
        raise UploadRejected(filename, "could not be opened as a PDF")
    if screening.encrypted:
        raise UploadRejected(filename, "password-protected; upload an unlocked copy")
    if screening.page_count > max_pages:
        raise UploadRejected(filename, f"more than {max_pages} pages")
    active = [name for name, found in (("JavaScript", screening.javascript),
                                       ("embedded files", screening.embedded_files),
                                       ("launch actions", screening.launch_action)) if found]
    if active:
        raise UploadRejected(filename, f"contains {', '.join(active)}")
    return screening
