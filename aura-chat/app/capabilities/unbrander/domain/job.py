"""A job: one project's PDFs, unbranded, and filed in a private Drive folder when
someone asks for it.

The status is stored, and the worker runs one step per status, so a restart
resumes where the last run stopped. UNBRANDING runs verify() inside every round.
A job then rests in UNBRANDED until filing is asked for, by the button or by
`file_when_done` at upload; FILING is a step of its own so a restart halfway
through the uploads finishes them without paying for the models again.
"""

import uuid
from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.domain import Organization

from .actions import Outcome, PageKind, Sorting, Usage
from .verify import Check, Finding, HitList


class JobStatus(StrEnum):
    RECEIVED = "RECEIVED"
    UNBRANDING = "UNBRANDING"
    UNBRANDED = "UNBRANDED"  # cleaned; waits here until filing is asked for
    FILING = "FILING"
    FILED_PRIVATE = "FILED_PRIVATE"
    FAILED = "FAILED"


# Statuses the worker has nothing to do for. ended_at is stamped on entering one,
# and the volume files are evicted counting from it: an UNBRANDED job nobody files
# loses its files after the retention period, like a finished one.
ENDED = frozenset({JobStatus.UNBRANDED, JobStatus.FILED_PRIVATE, JobStatus.FAILED})


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
    # File in Drive straight after unbranding, without waiting for someone to look.
    file_when_done: bool = False
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
    findings: list[Finding] = Field(default_factory=list)  # pages in source numbers
    rounds: int | None = None
    usage: dict[str, Usage] = Field(default_factory=dict)
    cost_usd: float | None = None
    drive_file_id: str | None = None
    started_at: datetime | None = None

    @computed_field
    @property
    def page_map(self) -> dict[int, int | None]:
        """Each source page and the output page made from it; None when dropped."""
        return page_map(self.page_count, self.dropped_pages)


class JobSummary(BaseModel):
    """A job as a list shows it."""

    id: str
    status: JobStatus
    uploader: str
    instructions: str | None
    project: str
    builder: str
    short_forms: list[str]
    city: str
    province: str
    dry_run: bool
    file_when_done: bool = False
    drive_folder_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None


class Job(JobSummary):
    organization: Organization
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


def page_map(page_count: int, dropped_pages: list[int]) -> dict[int, int | None]:
    gone = set(dropped_pages)
    out: dict[int, int | None] = {}
    output_page = 0
    for page in range(1, page_count + 1):
        if page in gone:
            out[page] = None
        else:
            output_page += 1
            out[page] = output_page
    return out


def in_source_pages(findings: list[Finding], page_count: int,
                    dropped_pages: list[int]) -> list[Finding]:
    """verify() reads the output, so its pages are output numbers; the judge's are
    source numbers already. Stored findings all use source numbers, the ones a
    reviewer sees beside the source page. A page with no source page (a count
    mismatch verify() itself reports) loses its number rather than point at the
    wrong page."""
    source_of = {output: source for source, output in page_map(page_count, dropped_pages).items()
                 if output is not None}
    return [finding if finding.check is Check.VISUAL or finding.page is None
            else finding.model_copy(update={"page": source_of.get(finding.page)})
            for finding in findings]


# Names of the filed PDFs. Never the upload's own name: a builder's file name
# ("Arista_SouthCal_Pricelist.pdf") is branding too.
TITLES = {"price_list": "Price List", "floor_plan": "Floor Plan", "site_plan": "Site Plan",
          "feature_sheet": "Features", "terms": "Terms", "elevation": "Elevations"}
UNTYPED_TITLE = "Document"


def file_names(documents: list[JobDocument]) -> dict[str, str]:
    """"Price List.pdf", and "Floor Plan 1.pdf", "Floor Plan 2.pdf" when there are several."""
    titles = {document.id: TITLES.get(document.doc_type or "", UNTYPED_TITLE)
              for document in documents}
    counts = Counter(titles.values())
    seen: Counter[str] = Counter()
    names = {}
    for document in documents:
        title = titles[document.id]
        seen[title] += 1
        names[document.id] = (f"{title} {seen[title]}.pdf" if counts[title] > 1
                              else f"{title}.pdf")
    return names


def filed(documents: list[JobDocument]) -> list[JobDocument]:
    """The documents FILING uploads, in upload order."""
    return [document for document in documents
            if document.status in (DocumentStatus.VERIFIED, DocumentStatus.FILED)]
