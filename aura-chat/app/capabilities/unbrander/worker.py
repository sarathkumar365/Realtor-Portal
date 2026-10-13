"""The job worker: takes one job at a time from RECEIVED to FILED_PRIVATE.

Each status is a step, and every step is safe to run again, so a restart picks a
job up where the last run stopped. The job's hold is a Postgres advisory lock
(JobStore.claim): a second worker, such as the old one during a deploy, skips it.

The unbrand step runs in a thread with its own event loop. The PDF work is plain
synchronous pymupdf, and on the service's own loop it would freeze every chat
answer for as long as a document takes.
"""

import asyncio
import hashlib
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .domain import (
    AddMark,
    Brief,
    DocumentStatus,
    Job,
    JobDocument,
    JobEvent,
    JobStatus,
    document_type,
    project_folders,
    subfolder,
)
from .files import JobFiles
from .ports import (
    DriveWriteFailed,
    GoogleWriter,
    JobStore,
    OcrUnavailable,
    PdfEditor,
    PdfInspector,
    UnbrandModels,
)
from .unbrand import Unbranded, unbrand_document

log = logging.getLogger("aura.unbrander")

AGENT = "agent"
IDLE_S = 5.0
SWEEP_EVERY = timedelta(hours=1)
# Names of the filed PDFs. Never the upload's own name: a builder's file name
# ("Arista_SouthCal_Pricelist.pdf") is branding too.
TITLES = {"price_list": "Price List", "floor_plan": "Floor Plan", "site_plan": "Site Plan",
          "feature_sheet": "Features", "terms": "Terms", "elevation": "Elevations"}
UNTYPED_TITLE = "Document"


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    drive_root_folder_id: str
    drive_test_root_folder_id: str
    max_repair_rounds: int = 2
    docs_per_day: int = 30
    doc_timeout_s: float = 600.0
    retention_days: int = 30


class Worker:
    def __init__(self, *, jobs: JobStore, drive: GoogleWriter, files: JobFiles,
                 editor: PdfEditor, inspector: PdfInspector,
                 new_models: Callable[[], UnbrandModels], settings: WorkerSettings,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._jobs = jobs
        self._drive = drive
        self._files = files
        self._editor = editor
        self._inspector = inspector
        self._new_models = new_models
        self._settings = settings
        self._now = now
        self._sleep = sleep
        self._last_sweep: datetime | None = None

    async def run_forever(self) -> None:
        while True:
            try:
                worked = await self.run_once()
                await self.sweep_if_due()
            except asyncio.CancelledError:
                raise
            except Exception:  # the loop outlives any one failure; the next pass retries
                log.exception("job worker pass failed")
                worked = False
            if not worked:
                await self._sleep(IDLE_S)

    async def run_once(self) -> bool:
        """Advance the oldest open job as far as it will go. False when there was
        nothing to do, or the job is waiting for tomorrow's budget."""
        async with self._jobs.claim() as job:
            if job is None:
                return False
            return await self._advance(job)

    async def sweep_if_due(self) -> None:
        now = self._now()
        if self._last_sweep and now - self._last_sweep < SWEEP_EVERY:
            return
        self._last_sweep = now
        cutoff = now - timedelta(days=self._settings.retention_days)
        for job_id in await self._jobs.ended_before(cutoff):
            if self._files.evict(job_id):
                await self._event(job_id, "evict files", "ok",
                                  {"reason": f"ended more than {self._settings.retention_days}"
                                             " days ago"})

    async def _advance(self, job: Job) -> bool:
        try:
            if job.status is JobStatus.RECEIVED:
                await self._move(job, JobStatus.UNBRANDING)
            if job.status is JobStatus.UNBRANDING:
                if not await self._unbrand(job):
                    return False
                if not any(document.status is DocumentStatus.VERIFIED for document in job.documents):
                    await self._fail(job, "no document passed verification")
                    return True
                await self._move(job, JobStatus.FILING)
            if job.status is JobStatus.FILING:
                await self._file(job)
                await self._move(job, JobStatus.FILED_PRIVATE)
        except (OcrUnavailable, DriveWriteFailed) as error:
            await self._fail(job, f"{type(error).__name__}: {error}")
        except FileNotFoundError as error:
            # The volume lost the job's files (a deploy without a volume, or one
            # wiped). Retrying cannot bring them back, and the oldest open job
            # would otherwise block the queue for good.
            await self._fail(job, f"a file is missing from the volume: {error.filename}")
        return True

    async def _unbrand(self, job: Job) -> bool:
        for document in job.documents:
            if document.status not in (DocumentStatus.PENDING, DocumentStatus.UNBRANDING):
                continue
            if await self._over_daily_cap():
                log.info("job %s waits: daily document cap reached", job.id)
                return False
            await self._unbrand_document(job, document)
        return True

    async def _over_daily_cap(self) -> bool:
        now = self._now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return await self._jobs.documents_started_since(midnight) >= self._settings.docs_per_day

    async def _unbrand_document(self, job: Job, document: JobDocument) -> None:
        document.status = DocumentStatus.UNBRANDING
        document.started_at = document.started_at or self._now()
        await self._jobs.update_document(document)
        brief = Brief(hits=job.hits, page_count=document.page_count,
                      instructions=job.instructions, organization=job.organization)
        source = self._files.source(job.id, document.position)
        try:
            done, models = await asyncio.to_thread(self._unbrand_in_thread, source, brief)
        except OcrUnavailable:
            raise
        except TimeoutError:
            await self._document_failed(
                job, document, f"took longer than {self._settings.doc_timeout_s:g} s")
            return
        except Exception as error:  # noqa: BLE001 -- a model or tool error fails this document, not the job
            await self._document_failed(job, document, f"{type(error).__name__}: {error}")
            return

        self._files.save_output(job.id, document.position, done.pdf)
        document.status = (DocumentStatus.VERIFIED if done.report.passed
                           else DocumentStatus.BLOCKED)
        document.doc_type = document_type(done.sorting)
        document.dropped_pages = done.dropped_pages
        document.removed_items = [outcome for outcome in done.outcomes
                                  if outcome.ok and not isinstance(outcome.action, AddMark)]
        document.findings = [*done.report.findings, *done.judge]
        document.rounds = done.rounds
        document.usage = dict(models.usage)
        document.cost_usd = round(sum(usage.cost for usage in models.usage.values()), 4)
        await self._jobs.update_document(document)
        await self._event(job.id, "unbrand", document.status.value.lower(), {
            "rounds": done.rounds, "cost_usd": document.cost_usd,
            "dropped_pages": done.dropped_pages, "findings": len(document.findings),
            "dropped_steps": done.dropped_steps,
            "input_sha256": document.sha256,
            "output_sha256": hashlib.sha256(done.pdf).hexdigest(),
        }, document_id=document.id)

    def _unbrand_in_thread(self, source: bytes, brief: Brief) -> tuple[Unbranded, UnbrandModels]:
        """Runs on a worker thread, in a loop of its own. The models are made here
        so their HTTP clients belong to this loop, and the timeout cancels the
        work in this loop rather than abandoning a thread that keeps spending."""
        models = self._new_models()
        done = asyncio.run(asyncio.wait_for(
            unbrand_document(source, brief, editor=self._editor, inspector=self._inspector,
                             models=models, max_repair_rounds=self._settings.max_repair_rounds),
            timeout=self._settings.doc_timeout_s,
        ))
        return done, models

    async def _document_failed(self, job: Job, document: JobDocument, reason: str) -> None:
        document.status = DocumentStatus.FAILED
        await self._jobs.update_document(document)
        await self._event(job.id, "unbrand", "failed", {"reason": reason},
                          document_id=document.id)

    async def _file(self, job: Job) -> None:
        root = (self._settings.drive_test_root_folder_id if job.dry_run
                else self._settings.drive_root_folder_id)
        folder, existed = root, False
        for name in project_folders(job):
            folder, existed = await self._drive.find_or_create_folder(folder, name)
        if existed and job.drive_folder_id != folder:
            # Filed beside what is there, never over it. Publishing decides
            # whether this job is an update to an existing project. A folder this
            # job made before a restart is not "existing".
            await self._event(job.id, "file", "existing project folder", {"folder_id": folder})
        if job.drive_folder_id != folder:
            await self._jobs.set_drive_folder(job.id, folder)
            job.drive_folder_id = folder

        filed = [document for document in job.documents
                 if document.status in (DocumentStatus.VERIFIED, DocumentStatus.FILED)]
        names = _file_names(filed)
        for document in filed:
            if document.drive_file_id:
                continue  # uploaded before a restart: FILING is repeated, the upload is not
            target = folder
            if sub := subfolder(document, filed):
                target, _ = await self._drive.find_or_create_folder(folder, sub)
            document.drive_file_id = await self._drive.upload_pdf(
                target, names[document.id], self._files.output(job.id, document.position))
            document.status = DocumentStatus.FILED
            await self._jobs.update_document(document)
            await self._event(job.id, "upload", "ok",
                              {"name": names[document.id], "file_id": document.drive_file_id,
                               "dry_run": job.dry_run}, document_id=document.id)

    async def _move(self, job: Job, status: JobStatus) -> None:
        await self._jobs.set_status(job.id, status)
        await self._event(job.id, "status", status.value)
        job.status = status

    async def _fail(self, job: Job, reason: str) -> None:
        await self._jobs.set_status(job.id, JobStatus.FAILED, error=reason)
        await self._event(job.id, "status", JobStatus.FAILED.value, {"reason": reason})
        job.status = JobStatus.FAILED
        log.warning("job %s failed: %s", job.id, reason)

    async def _event(self, job_id: str, action: str, result: str, detail: dict | None = None,
                     *, document_id: str | None = None) -> None:
        await self._jobs.add_event(JobEvent(job_id=job_id, document_id=document_id, actor=AGENT,
                                            action=action, result=result, detail=detail or {}))


def _file_names(documents: list[JobDocument]) -> dict[str, str]:
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
