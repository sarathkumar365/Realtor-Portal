"""Admin-only API for Unbrander jobs: upload a project's PDFs, follow the job,
review each document page by page, and file it in Drive.

Uploads are accepted while the worker is switched off; they wait in RECEIVED. A
job rests in UNBRANDED until filing is asked for: at upload with `file_when_done`,
or later with POST .../file. The same API serves a person and an agent.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ValidationError

from app.api import container, current_claims
from app.domain import Brand, Claims

from .domain import (
    Job,
    JobCounts,
    JobDocument,
    JobEvent,
    JobStatus,
    JobSummary,
    NewDocument,
    NewJob,
    file_names,
    filed,
)
from .intake import UploadRejected, check_upload
from .ports import PdfEditor

router = APIRouter(prefix="/admin/unbrander")
log = logging.getLogger("aura.audit")

MAX_FILES = 10
UNAVAILABLE = "Unbrander is not available: no database is configured"
NO_DRIVE = "Drive is not set up on this service: download the cleaned PDFs instead"
NO_WORKER = "the Unbrander worker is switched off on this service, so nothing would be filed"
# Enough to read a price list on a desktop screen; a 24x36 in site plan is still
# under 4000 pixels on its long side.
PAGE_DPI = 110
# A document's files never change once written, so a page image may be cached;
# private, because it is behind the admin's token.
PAGE_CACHE = "private, max-age=3600"


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus


class JobDetail(Job):
    events: list[JobEvent]


class UploadLimits(BaseModel):
    max_files: int
    max_file_mb: int
    max_pages: int
    can_file: bool  # Drive is set up and the worker runs: filing would happen


class JobList(BaseModel):
    jobs: list[JobSummary]
    # Each job's documents by job id, when asked for with documents=true: what a
    # card needs (pages, changes) in one request instead of one per job.
    documents: dict[str, list[JobDocument]] | None = None


def _require_admin(claims: Claims) -> None:
    if not claims.is_admin:
        raise HTTPException(status_code=403, detail="admin only")


def _admin(request: Request, claims: Claims):
    _require_admin(claims)
    services = container(request)
    if services.jobs is None or services.job_files is None or services.pdf_inspector is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return services


@router.get("/limits")
async def upload_limits(request: Request, claims: Claims = Depends(current_claims)) -> UploadLimits:
    """What an upload may be, so a client checks against the server's own numbers
    instead of a copy of them. Admin only."""
    _require_admin(claims)
    services = container(request)
    settings = services.settings
    return UploadLimits(max_files=MAX_FILES, max_file_mb=settings.unbrander_max_file_mb,
                        max_pages=settings.unbrander_max_pages,
                        can_file=_filing_problem(services) is None)


def _since(since: datetime | None) -> datetime:
    """The start of the period a count covers. The client sends it because the
    period is the brokerage's month, in its own time zone; without one, the
    current month in UTC."""
    if since is None:
        return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return since if since.tzinfo else since.replace(tzinfo=UTC)


@router.get("/summary")
async def summary(request: Request, since: datetime | None = None,
                  claims: Claims = Depends(current_claims)) -> JobCounts:
    """Jobs waiting for review and running now, and jobs and cleaned pages since
    `since`. Admin only."""
    _require_admin(claims)
    jobs = container(request).jobs
    if jobs is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return await jobs.counts(_since(since))


@router.post("/jobs", status_code=202)
async def create_job(
    request: Request,
    files: list[UploadFile] = File(...),
    project: str = Form(...),
    builder: str = Form(...),
    city: str = Form(...),
    short_forms: str = Form(""),
    province: str = Form("Ontario"),
    instructions: str | None = Form(None),
    file_when_done: bool = Form(False),
    claims: Claims = Depends(current_claims),
) -> JobAccepted:
    """Upload one project's PDFs with what is known about them. With
    `file_when_done`, the job is filed in Drive as soon as it is unbranded;
    without it, it waits in UNBRANDED for POST .../file. Admin only."""
    services = _admin(request, claims)
    if not 1 <= len(files) <= MAX_FILES:
        raise HTTPException(status_code=422, detail=f"upload 1 to {MAX_FILES} PDFs")
    if file_when_done and (problem := _filing_problem(services)):
        # Refused now, not discovered after the models have been paid for.
        raise HTTPException(status_code=422, detail=problem)
    settings = services.settings
    job_id = str(uuid.uuid4())
    documents = []
    try:
        for position, upload in enumerate(files, start=1):
            name = upload.filename or f"file {position}"
            # Refused before reading: the size is known from the spooled upload,
            # and reading an oversized file first would hold it all in memory.
            if upload.size is not None and upload.size > settings.unbrander_max_file_mb * 2**20:
                raise UploadRejected(name, f"larger than {settings.unbrander_max_file_mb} MB",
                                     too_large=True)
            data = await upload.read()
            screening = check_upload(name, data, inspector=services.pdf_inspector,
                                     max_mb=settings.unbrander_max_file_mb,
                                     max_pages=settings.unbrander_max_pages)
            # On the volume before the row exists, so the worker never claims a
            # job whose files are not there yet.
            services.job_files.save_source(job_id, position, data)
            documents.append(NewDocument(filename=name, sha256=hashlib.sha256(data).hexdigest(),
                                         page_count=screening.page_count))
        new = NewJob(
            id=job_id, uploader=claims.user, project=project.strip(), builder=builder.strip(),
            short_forms=[form.strip() for form in short_forms.split(",") if form.strip()],
            city=city.strip(), province=province.strip() or "Ontario",
            instructions=(instructions or "").strip() or None,
            organization=services.organization, dry_run=settings.unbrander_dry_run,
            file_when_done=file_when_done, documents=documents,
        )
        job = await services.jobs.create(new)
    except UploadRejected as error:
        services.job_files.evict(job_id)
        _audit(claims, "upload rejected", str(error))
        raise HTTPException(status_code=413 if error.too_large else 422,
                            detail=str(error)) from error
    except ValidationError as error:
        services.job_files.evict(job_id)
        raise HTTPException(status_code=422, detail=error.errors(include_url=False,
                                                                 include_context=False)) from error
    except Exception as error:
        services.job_files.evict(job_id)
        log.warning("could not create an unbrander job: %s: %s", type(error).__name__, error)
        raise HTTPException(status_code=503, detail="could not save the job") from error

    try:
        await services.jobs.add_event(JobEvent(
            job_id=job.id, actor=claims.user, action="upload", result="accepted",
            detail={"files": [document.filename for document in documents],
                    "dry_run": job.dry_run, "instructions": job.instructions is not None,
                    "file_when_done": job.file_when_done},
        ))
    except Exception as error:  # noqa: BLE001 -- the job exists; a 500 would invite a duplicate
        log.warning("job %s created but its upload event was not saved: %s: %s",
                    job.id, type(error).__name__, error)
    _audit(claims, "upload accepted", job.id)
    return JobAccepted(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request,
                  claims: Claims = Depends(current_claims)) -> JobDetail:
    """One job with its documents and its audit log. Admin only."""
    services = _admin(request, claims)
    job = await _job(services, job_id)
    return JobDetail(**dict(job), events=await services.jobs.events(job_id))


@router.post("/jobs/{job_id}/file", status_code=202)
async def file_job(job_id: str, request: Request,
                   claims: Claims = Depends(current_claims)) -> JobAccepted:
    """File an unbranded job in Drive: the worker uploads its passing documents to
    the project's private folder. Only from UNBRANDED. Admin only."""
    services = _admin(request, claims)
    if problem := _filing_problem(services):
        raise HTTPException(status_code=503, detail=problem)
    job = await _job(services, job_id)
    if job.status is not JobStatus.UNBRANDED:
        raise HTTPException(status_code=409,
                            detail=f"only an unbranded job can be filed; this one is {job.status}")
    if not all(services.job_files.has_output(job_id, document.position)
               for document in filed(job.documents)):
        # Evicted after the retention period. Filing would fail the job halfway;
        # the cleaned files are gone either way.
        raise HTTPException(status_code=410, detail="this job's cleaned files were removed after"
                            f" {services.settings.unbrander_retention_days} days; upload it again")
    # One statement: a double click or an agent's retry sends it to filing once.
    if not await services.jobs.move(job_id, JobStatus.UNBRANDED, JobStatus.FILING):
        raise HTTPException(status_code=409, detail="this job is already being filed")
    try:
        await services.jobs.add_event(JobEvent(job_id=job_id, actor=claims.user, action="file",
                                               result="requested"))
    except Exception as error:  # noqa: BLE001 -- filing is under way; a 500 would invite a repeat
        log.warning("job %s sent to filing but its event was not saved: %s: %s",
                    job_id, type(error).__name__, error)
    _audit(claims, "file requested", job_id)
    return JobAccepted(job_id=job_id, status=JobStatus.FILING)


@router.get("/jobs")
async def list_jobs(request: Request, status: list[JobStatus] = Query(default=[]), limit: int = 50,
                    documents: bool = False, claims: Claims = Depends(current_claims)) -> JobList:
    """Jobs, newest first, in any of the given statuses (repeat `status`), without
    documents unless `documents=true`. Admin only."""
    services = _admin(request, claims)
    jobs = await services.jobs.recent(statuses=status, limit=min(max(limit, 1), 200),
                                      documents=documents)
    return JobList(jobs=[JobSummary(**job.model_dump(include=set(JobSummary.model_fields)))
                         for job in jobs],
                   documents={job.id: job.documents for job in jobs} if documents else None)


@router.get("/jobs/{job_id}/documents/{position}/pages/{page}.jpg",
            response_class=Response, responses={200: {"content": {"image/jpeg": {}}}})
async def page_image(job_id: str, position: int, page: int, request: Request,
                     version: Literal["source", "output"] = "source",
                     claims: Claims = Depends(current_claims)) -> Response:
    """One page of a document as a JPEG. `page` is always the source page number,
    for the output too, so a reviewer pairs the two without counting dropped
    pages. Admin only."""
    services = _admin(request, claims)
    editor = _editor(services)
    document = _document(await _job(services, job_id), position)
    if not 1 <= page <= document.page_count:
        raise HTTPException(status_code=404, detail=f"no page {page}")
    if version == "source":
        pdf, shown = _read(services.job_files.source, job_id, position), page
    else:
        shown = document.page_map[page]
        if shown is None:
            raise HTTPException(status_code=404, detail=f"page {page} was dropped")
        pdf = _read(services.job_files.output, job_id, position)
    image = await asyncio.to_thread(_render, editor, pdf, shown)
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": PAGE_CACHE})


@router.get("/jobs/{job_id}/documents/{position}/output.pdf",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
async def output_pdf(job_id: str, position: int, request: Request,
                     claims: Claims = Depends(current_claims)) -> Response:
    """The cleaned PDF, under the name it is filed with. Admin only."""
    services = _admin(request, claims)
    job = await _job(services, job_id)
    document = _document(job, position)
    pdf = _read(services.job_files.output, job_id, position)
    to_file = filed(job.documents)
    # A blocked document is never filed; it is named as if it were the only one.
    names = file_names(to_file if document in to_file else [document])
    _audit(claims, "download", f"{job_id}/{position}")
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{names[document.id]}"',
        "Cache-Control": "private, no-store",
    })


@router.post("/mark-preview", response_class=Response,
             responses={200: {"content": {"image/jpeg": {}}}})
async def mark_preview(brand: Brand, request: Request,
                       claims: Claims = Depends(current_claims)) -> Response:
    """The mark as a brand would print it, before the profile is saved. Admin only."""
    _require_admin(claims)
    image = await asyncio.to_thread(_editor(container(request)).preview_mark, brand)
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _filing_problem(services) -> str | None:
    """Why a job could not be filed on this service, or None when it could."""
    if services.drive is None:
        return NO_DRIVE
    if services.worker is None:
        return NO_WORKER
    return None


async def _job(services, job_id: str) -> Job:
    job = await services.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return job


def _document(job: Job, position: int) -> JobDocument:
    for document in job.documents:
        if document.position == position:
            return document
    raise HTTPException(status_code=404, detail=f"no document {position}")


def _editor(services) -> PdfEditor:
    if services.pdf_editor is None:
        raise HTTPException(status_code=503, detail="the PDF editor is not configured")
    return services.pdf_editor


def _read(load, job_id: str, position: int) -> bytes:
    try:
        return load(job_id, position)
    except FileNotFoundError as error:
        # Output appears when the document is unbranded; both go when the job's
        # files are evicted after the retention period.
        raise HTTPException(status_code=404, detail="the file is not on the volume") from error


def _render(editor: PdfEditor, pdf: bytes, page: int) -> bytes:
    session = editor.open(pdf)
    try:
        return session.render(page, PAGE_DPI)
    finally:
        session.close()


def _audit(claims: Claims, action: str, detail: str) -> None:
    log.info(json.dumps({"event": "unbrander", "user": claims.user, "action": action,
                         "detail": detail}))
