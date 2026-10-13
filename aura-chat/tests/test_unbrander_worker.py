"""The job worker over fakes: a job store, a Drive, a PDF store and scripted models."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.capabilities.unbrander.domain import (
    DocumentStatus,
    JobStatus,
    NewDocument,
    NewJob,
    PageSort,
    Sorting,
    Word,
)
from app.capabilities.unbrander.files import JobFiles
from app.capabilities.unbrander.ports import OcrUnavailable
from app.capabilities.unbrander.worker import Worker, WorkerSettings
from app.domain import Organization
from tests.fakes import FakeGoogleWriter, FakeJobStore, FakePdfStore, FakeUnbrandModels

SOURCE = b"source"
SETTINGS = WorkerSettings(drive_root_folder_id="real-root", drive_test_root_folder_id="test-root")


def words(text: str) -> list[Word]:
    out, left = [], 50.0
    for token in text.split():
        out.append(Word(text=token, bbox=(left, 100, left + 10 * len(token), 112)))
        left += 10 * len(token) + 5
    return out


def sorting(kind: str, keep: bool = True) -> Sorting:
    return Sorting(pages=[PageSort(page=1, kind=kind, keep=keep, why=kind)], terms=[])


class Setup:
    def __init__(self, tmp_path, *kinds: str, page: str = "Lot 12 $1,234,567", **settings):
        self.jobs = FakeJobStore()
        self.drive = FakeGoogleWriter()
        self.files = JobFiles(tmp_path)
        self.pdfs = FakePdfStore(SOURCE, [words(page)])
        self.kinds = list(kinds)
        self.models_made = 0
        self.models_class = FakeUnbrandModels
        self.clock = datetime(2026, 10, 13, 15, tzinfo=UTC)
        self.worker = Worker(jobs=self.jobs, drive=self.drive, files=self.files,
                             editor=self.pdfs, inspector=self.pdfs, new_models=self.new_models,
                             settings=replace(SETTINGS, **settings),
                             now=lambda: self.clock)

    def new_models(self) -> FakeUnbrandModels:
        kind = self.kinds[self.models_made % len(self.kinds)]
        self.models_made += 1
        return self.models_class(sorting(kind))

    async def job(self, documents: int = 1, dry_run: bool = True) -> str:
        new = NewJob(uploader="admin", project="SouthCal", builder="Arista Homes", city="Vaughan",
                     organization=Organization(), dry_run=dry_run,
                     documents=[NewDocument(filename=f"Arista_SouthCal_{i}.pdf", sha256="s",
                                            page_count=1) for i in range(1, documents + 1)])
        for position in range(1, documents + 1):
            self.files.save_source(new.id, position, SOURCE)
        return (await self.jobs.create(new)).id

    def filed_paths(self) -> dict[str, list[str]]:
        return {name: self.drive.path_of(folder)
                for folder, files in self.drive.files.items() for name, _ in files}


async def test_a_job_runs_from_received_to_filed_private_in_the_test_folder(tmp_path):
    setup = Setup(tmp_path, "price_list", "floor_plan")
    job_id = await setup.job(documents=2)
    assert await setup.worker.run_once()
    job = await setup.jobs.get(job_id)
    assert job.status is JobStatus.FILED_PRIVATE and job.ended_at
    assert [d.status for d in job.documents] == [DocumentStatus.FILED] * 2
    assert [d.doc_type for d in job.documents] == ["price_list", "floor_plan"]
    project = ["test-root", "Ontario", "Vaughan", "SouthCal - Arista Homes"]
    assert setup.filed_paths() == {"Price List.pdf": project[1:], "Floor Plan.pdf": project[1:]}
    assert setup.drive.folders[("test-root", "Ontario")]  # dry run: never the real root
    steps = [(e.action, e.result) for e in await setup.jobs.events(job_id)]
    assert steps == [("status", "UNBRANDING"), ("unbrand", "verified"), ("unbrand", "verified"),
                     ("status", "FILING"), ("upload", "ok"), ("upload", "ok"),
                     ("status", "FILED_PRIVATE")]


async def test_a_real_run_files_under_the_real_root(tmp_path):
    setup = Setup(tmp_path, "price_list")
    await setup.job(dry_run=False)
    await setup.worker.run_once()
    assert ("real-root", "Ontario") in setup.drive.folders
    assert ("test-root", "Ontario") not in setup.drive.folders


async def test_several_floor_plans_go_in_their_own_folder_with_numbered_names(tmp_path):
    setup = Setup(tmp_path, "floor_plan", "floor_plan", "price_list")
    await setup.job(documents=3)
    await setup.worker.run_once()
    paths = setup.filed_paths()
    assert paths["Floor Plan 1.pdf"][-1] == paths["Floor Plan 2.pdf"][-1] == "Floor Plans"
    assert paths["Price List.pdf"][-1] == "SouthCal - Arista Homes"


async def test_the_builders_file_name_never_reaches_drive(tmp_path):
    setup = Setup(tmp_path, "price_list")
    await setup.job()
    await setup.worker.run_once()
    assert not any("Arista" in name for name in setup.drive.uploads)


async def test_a_blocked_document_is_kept_but_not_filed(tmp_path):
    # Page 1 of the second document keeps the builder's name: verify() blocks it.
    setup = Setup(tmp_path, "price_list")
    job_id = await setup.job(documents=1)
    blocked = Setup(tmp_path, "price_list", page="Arista Homes Lot 12")
    blocked_id = await blocked.job()
    await setup.worker.run_once()
    await blocked.worker.run_once()
    assert (await setup.jobs.get(job_id)).status is JobStatus.FILED_PRIVATE
    job = await blocked.jobs.get(blocked_id)
    assert job.documents[0].status is DocumentStatus.BLOCKED
    assert job.status is JobStatus.FAILED and job.error == "no document passed verification"
    assert blocked.drive.uploads == []
    assert blocked.files.output(blocked_id, 1)  # kept on the volume for the approver


async def test_a_restart_in_filing_uploads_only_what_is_missing_and_calls_no_model(tmp_path):
    setup = Setup(tmp_path, "price_list", "site_plan")
    job_id = await setup.job(documents=2)
    real_upload = setup.drive.upload_pdf
    uploads = 0

    async def crash_on_second(folder_id, name, data):
        nonlocal uploads
        uploads += 1
        if uploads == 2:
            raise RuntimeError("process killed")
        return await real_upload(folder_id, name, data)

    setup.drive.upload_pdf = crash_on_second
    with pytest.raises(RuntimeError):
        await setup.worker.run_once()
    job = await setup.jobs.get(job_id)
    assert job.status is JobStatus.FILING
    assert [d.status for d in job.documents] == [DocumentStatus.FILED, DocumentStatus.VERIFIED]

    setup.drive.upload_pdf = real_upload
    models_before = setup.models_made
    await setup.worker.run_once()
    assert (await setup.jobs.get(job_id)).status is JobStatus.FILED_PRIVATE
    assert setup.drive.uploads == ["Price List.pdf", "Site Plan.pdf"]
    assert setup.models_made == models_before


async def test_a_restart_in_unbranding_runs_the_interrupted_document_again(tmp_path):
    setup = Setup(tmp_path, "price_list")
    job_id = await setup.job()
    await setup.jobs.set_status(job_id, JobStatus.UNBRANDING)
    document = (await setup.jobs.get(job_id)).documents[0]
    document.status = DocumentStatus.UNBRANDING
    await setup.jobs.update_document(document)
    await setup.worker.run_once()
    assert (await setup.jobs.get(job_id)).status is JobStatus.FILED_PRIVATE


async def test_the_daily_cap_makes_a_job_wait_until_tomorrow(tmp_path):
    setup = Setup(tmp_path, "price_list", docs_per_day=1)
    job_id = await setup.job(documents=2)
    assert not await setup.worker.run_once()
    job = await setup.jobs.get(job_id)
    assert job.status is JobStatus.UNBRANDING
    assert [d.status for d in job.documents] == [DocumentStatus.VERIFIED, DocumentStatus.PENDING]
    setup.clock += timedelta(days=1)
    assert await setup.worker.run_once()
    assert (await setup.jobs.get(job_id)).status is JobStatus.FILED_PRIVATE


async def test_a_document_over_its_time_budget_fails(tmp_path):
    setup = Setup(tmp_path, "price_list", doc_timeout_s=0.05)

    class Slow(FakeUnbrandModels):
        async def sort(self, brief, pages):
            await asyncio.sleep(5)

    setup.models_class = Slow
    job_id = await setup.job()
    await setup.worker.run_once()
    job = await setup.jobs.get(job_id)
    assert job.documents[0].status is DocumentStatus.FAILED
    assert job.status is JobStatus.FAILED
    detail = [e.detail for e in await setup.jobs.events(job_id) if e.result == "failed"]
    assert detail == [{"reason": "took longer than 0.05 s"}]


async def test_no_ocr_fails_the_job_rather_than_passing_unchecked_pixels(tmp_path):
    setup = Setup(tmp_path, "price_list")

    def no_ocr(pdf, *, ocr):
        if ocr:
            raise OcrUnavailable("tesseract language data not found")
        return FakePdfStore.inspect(setup.pdfs, pdf, ocr=ocr)

    setup.pdfs.inspect = no_ocr
    job_id = await setup.job()
    await setup.worker.run_once()
    job = await setup.jobs.get(job_id)
    assert job.status is JobStatus.FAILED and "OcrUnavailable" in job.error
    assert setup.drive.uploads == []


async def test_nothing_to_do_is_reported_so_the_loop_can_rest(tmp_path):
    assert not await Setup(tmp_path, "price_list").worker.run_once()


async def test_files_are_evicted_only_after_the_retention_period(tmp_path):
    setup = Setup(tmp_path, "price_list", retention_days=30)
    old, recent = await setup.job(), await setup.job()
    await setup.worker.run_once()
    await setup.worker.run_once()
    setup.jobs.jobs[old].ended_at = setup.clock - timedelta(days=31)
    setup.jobs.jobs[recent].ended_at = setup.clock - timedelta(days=29)
    await setup.worker.sweep_if_due()
    assert not (tmp_path / old).exists() and (tmp_path / recent).exists()
    assert [e.action for e in await setup.jobs.events(old)][-1] == "evict files"
    assert (await setup.jobs.get(old)) is not None  # the row and its log stay


async def test_a_job_whose_files_are_gone_fails_instead_of_blocking_the_queue(tmp_path):
    setup = Setup(tmp_path, "price_list")
    lost, next_job = await setup.job(), await setup.job()
    setup.files.evict(lost)
    await setup.worker.run_once()
    job = await setup.jobs.get(lost)
    assert job.status is JobStatus.FAILED and "missing from the volume" in job.error
    await setup.worker.run_once()
    assert (await setup.jobs.get(next_job)).status is JobStatus.FILED_PRIVATE


async def test_only_a_folder_another_job_made_counts_as_an_existing_project(tmp_path):
    setup = Setup(tmp_path, "price_list")
    first, second = await setup.job(), await setup.job()
    await setup.worker.run_once()
    await setup.worker.run_once()
    existing = {job_id: [e for e in await setup.jobs.events(job_id)
                         if e.result == "existing project folder"]
                for job_id in (first, second)}
    assert (len(existing[first]), len(existing[second])) == (0, 1)


async def test_a_restart_in_filing_does_not_call_its_own_folder_existing(tmp_path):
    setup = Setup(tmp_path, "price_list", "site_plan")
    job_id = await setup.job(documents=2)
    real_upload = setup.drive.upload_pdf

    async def crash(folder_id, name, data):
        setup.drive.upload_pdf = real_upload
        raise RuntimeError("process killed")

    setup.drive.upload_pdf = crash
    with pytest.raises(RuntimeError):
        await setup.worker.run_once()
    await setup.worker.run_once()
    assert (await setup.jobs.get(job_id)).status is JobStatus.FILED_PRIVATE
    assert not [e for e in await setup.jobs.events(job_id)
                if e.result == "existing project folder"]
