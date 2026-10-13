"""Admin-only API for Unbrander jobs: upload a project's PDFs, then follow the job.

Uploads are accepted while the worker is switched off; they wait in RECEIVED.
"""

import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from app.api import container, current_claims
from app.domain import Claims

from .domain import JobEvent, JobStatus, NewDocument, NewJob
from .intake import UploadRejected, check_upload

router = APIRouter(prefix="/admin/unbrander")
log = logging.getLogger("aura.audit")

MAX_FILES = 10
UNAVAILABLE = "Unbrander is not available: no database is configured"


def _admin(request: Request, claims: Claims):
    if not claims.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    services = container(request)
    if services.jobs is None or services.job_files is None or services.pdf_inspector is None:
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    return services


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
    claims: Claims = Depends(current_claims),
) -> dict:
    """Upload one project's PDFs with what is known about them. Admin only."""
    services = _admin(request, claims)
    if not 1 <= len(files) <= MAX_FILES:
        raise HTTPException(status_code=422, detail=f"upload 1 to {MAX_FILES} PDFs")
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
            documents=documents,
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
                    "dry_run": job.dry_run, "instructions": job.instructions is not None},
        ))
    except Exception as error:  # noqa: BLE001 -- the job exists; a 500 would invite a duplicate
        log.warning("job %s created but its upload event was not saved: %s: %s",
                    job.id, type(error).__name__, error)
    _audit(claims, "upload accepted", job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request,
                  claims: Claims = Depends(current_claims)) -> dict:
    """One job with its documents and its audit log. Admin only."""
    services = _admin(request, claims)
    job = await services.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return {**job.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in await services.jobs.events(job_id)]}


@router.get("/jobs")
async def list_jobs(request: Request, status: JobStatus | None = None, limit: int = 50,
                    claims: Claims = Depends(current_claims)) -> dict:
    """Jobs, newest first, without documents. Admin only."""
    services = _admin(request, claims)
    jobs = await services.jobs.recent(status=status, limit=min(max(limit, 1), 200))
    return {"jobs": [job.model_dump(mode="json", exclude={"documents", "organization"})
                     for job in jobs]}


def _audit(claims: Claims, action: str, detail: str) -> None:
    log.info(json.dumps({"event": "unbrander", "user": claims.user, "action": action,
                         "detail": detail}))
