"""A job: one project's PDFs on their way to a private Drive folder.

The status is stored, and the worker runs one step per status, so a restart
resumes where the last run stopped. UNBRANDING runs verify() inside every round;
FILING is a step of its own so a restart halfway through the uploads finishes
them without paying for the models again.
"""

import uuid
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.domain import Organization

from .actions import Outcome, PageKind, Sorting, Usage
from .verify import Finding, HitList


class JobStatus(StrEnum):
    RECEIVED = "RECEIVED"
    UNBRANDING = "UNBRANDING"
    FILING = "FILING"
    FILED_PRIVATE = "FILED_PRIVATE"
    FAILED = "FAILED"


ENDED = frozenset({JobStatus.FILED_PRIVATE, JobStatus.FAILED})


class DocumentStatus(StrEnum):
    PENDING = "PENDING"
    UNBRANDING = "UNBRANDING"
    VERIFIED = "VERIFIED"  # passed verify(); filed in FILING
    BLOCKED = "BLOCKED"    # failed verify(); kept on the volume for the approver, never filed
    FILED = "FILED"
    FAILED = "FAILED"


class NewDocument(BaseModel):
    filename: str
    sha256: str
    page_count: int


class NewJob(BaseModel):
    # Minted here, not by the store, so the upload's files are on the volume under
    # this id before the row exists: the worker never claims a job without them.
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    uploader: str
    project: str = Field(min_length=1)
    builder: str = Field(min_length=1)
    short_forms: list[str] = Field(default_factory=list)
    city: str = Field(min_length=1)
    province: str = "Ontario"
    instructions: str | None = None  # the operator's request; never overrides a guard
    organization: Organization  # copied, so a later profile edit does not rewrite this job
    dry_run: bool
    documents: list[NewDocument] = Field(min_length=1)


class JobDocument(BaseModel):
    id: str
    job_id: str
    position: int
    filename: str
    sha256: str
    page_count: int
    status: DocumentStatus
    doc_type: PageKind | None = None
    dropped_pages: list[int] = Field(default_factory=list)
    removed_items: list[Outcome] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    rounds: int | None = None
    usage: dict[str, Usage] = Field(default_factory=dict)
    cost_usd: float | None = None
    drive_file_id: str | None = None
    started_at: datetime | None = None


class Job(BaseModel):
    id: str
    status: JobStatus
    uploader: str
    instructions: str | None
    project: str
    builder: str
    short_forms: list[str]
    city: str
    province: str
    organization: Organization
    dry_run: bool
    drive_folder_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None
    documents: list[JobDocument] = Field(default_factory=list)

    @property
    def hits(self) -> HitList:
        return HitList(builder=self.builder, project=self.project, short_forms=self.short_forms)


class JobEvent(BaseModel):
    """One line of the audit log. Never edited once written."""

    job_id: str
    document_id: str | None = None
    actor: str  # "agent", or the user id of the person who acted
    action: str
    result: str
    detail: dict[str, Any] = Field(default_factory=dict)
    at: datetime | None = None  # set by the store


def document_type(sorting: Sorting) -> PageKind | None:
    """The most common kind among the pages kept; None when nothing was kept.

    Elevations count as floor plans: builders print them on the floor plan sheets,
    and the Drive folder rule only asks whether a document is a floor plan.
    """
    kinds = Counter("floor_plan" if page.kind == "elevation" else page.kind
                    for page in sorting.pages if page.keep)
    return kinds.most_common(1)[0][0] if kinds else None


FLOOR_PLANS_FOLDER = "Floor Plans"


def project_folders(job: Job) -> list[str]:
    """Folder names under the root, outermost first (LOOP.md, Drive filing)."""
    return [job.province, job.city, f"{job.project} - {job.builder}"]


def subfolder(document: JobDocument, filed: list[JobDocument]) -> str | None:
    """Floor plans get their own folder when there is more than one; every other
    document, and a single floor plan, sits at the project folder's root."""
    floor_plans = sum(1 for other in filed if other.doc_type == "floor_plan")
    return FLOOR_PLANS_FOLDER if document.doc_type == "floor_plan" and floor_plans > 1 else None
