"""The result of checking a cleaned PDF against its source.

Severity follows the verification gate in docs/feature/Unbrander/AUTONOMY.md:
RETRY gets one targeted retry and then becomes a flag, BLOCK stops publish
until a human resolves it, FLAG goes to the approver on the page it concerns.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from .pdf import BBox


class Check(StrEnum):
    TEXT_SWEEP = "text_sweep"
    RAW_BYTES = "raw_bytes"
    OCR_SWEEP = "ocr_sweep"
    NUMBERS = "numbers"
    PROVENANCE = "provenance"
    METADATA = "metadata"
    COVER_UP = "cover_up"
    PAGES = "pages"


class Severity(StrEnum):
    RETRY = "retry"
    BLOCK = "block"
    FLAG = "flag"


class HitList(BaseModel):
    """The names that must not survive. `extras` are phones, URLs, emails and
    addresses found in the source."""

    builder: str
    project: str
    short_forms: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)

    def terms(self) -> list[str]:
        seen: dict[str, str] = {}
        for t in [self.builder, self.project, *self.short_forms, *self.extras]:
            t = t.strip()
            # A term with no letter or digit ("@", "—") would match everywhere.
            if any(c.isalnum() for c in t):
                seen.setdefault(t.lower(), t)
        return list(seen.values())


class Finding(BaseModel):
    check: Check
    severity: Severity
    detail: str
    page: int | None = None
    bbox: BBox | None = None


class VerifyReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Flags alone do not stop a document; they travel to the approver."""
        return not any(f.severity is not Severity.FLAG for f in self.findings)
