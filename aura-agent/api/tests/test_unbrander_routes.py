"""The admin API for Unbrander jobs, over the fake job store and the real intake check."""

import asyncio

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.capabilities.unbrander.adapters.pdf_edit_pymupdf import PyMuPdfEditor
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.domain import DocumentStatus, JobStatus
from app.capabilities.unbrander.files import JobFiles
from app.domain import Claims, Organization, Role
from tests.fakes import FakeAuthVerifier, FakeGoogleWriter, FakeJobStore

AUTH = {"Authorization": "Bearer token"}
FIELDS = {"project": "SouthCal", "builder": "Arista Homes", "city": "Vaughan",
          "short_forms": "AH, SC", "instructions": "drop the sales centre map"}


def pdf(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page().insert_text((72, 72), "Lot 12")
    return doc.tobytes()


@pytest.fixture
def unbrander(app, tmp_path):
    services = app.state.container
    services.auth = FakeAuthVerifier(Claims(user="sudhanshu", role=Role.ADMIN, issued_ms=0))
    services.jobs = FakeJobStore()
    services.job_files = JobFiles(tmp_path)
    # The real inspector: screening is cheap and these PDFs are built in the test.
    services.pdf_inspector = PyMuPdfInspector()
    services.pdf_editor = PyMuPdfEditor()
    services.drive = None  # Drive is optional; tests that file set it
    services.worker = None
    return services


class IdleWorker:
    """Stands in for a running worker: the app starts it, and it does nothing."""

    async def run_forever(self) -> None:
        await asyncio.Event().wait()


def can_file(services) -> None:
    """Drive set up and a worker running: what filing needs on this service."""
    services.drive = FakeGoogleWriter()
    services.worker = IdleWorker()
    services.ocr_problem = lambda: None


def upload(app, files, fields=FIELDS, headers=AUTH):
    with TestClient(app) as client:
        return client.post("/admin/unbrander/jobs", data=fields, headers=headers,
                           files=[("files", (name, data, "application/pdf"))
                                  for name, data in files])


def test_an_admin_upload_creates_a_received_job_with_its_files_on_the_volume(app, unbrander,
                                                                          tmp_path):
    response = upload(app, [("prices.pdf", pdf(2)), ("plans.pdf", pdf(5))])
    assert response.status_code == 202
    job = unbrander.jobs.jobs[response.json()["job_id"]]
    assert job.status.value == "RECEIVED" and job.uploader == "sudhanshu"
    assert (job.short_forms, job.instructions) == (["AH", "SC"], "drop the sales centre map")
    assert [(d.filename, d.page_count) for d in job.documents] == [("prices.pdf", 2),
                                                                   ("plans.pdf", 5)]
    assert job.dry_run and job.organization == Organization()
    assert (tmp_path / job.id / "source" / "1.pdf").exists()
    assert [(e.actor, e.action) for e in unbrander.jobs.event_log] == [("sudhanshu", "upload")]


def test_a_realtor_cannot_upload(app, unbrander):
    unbrander.auth = FakeAuthVerifier()
    assert upload(app, [("prices.pdf", pdf())]).status_code == 403
    assert unbrander.jobs.jobs == {}


def test_a_file_that_is_not_a_pdf_is_refused_and_nothing_is_kept(app, unbrander, tmp_path):
    response = upload(app, [("prices.pdf", pdf()), ("notes.pdf", b"PK\x03\x04 docx")])
    assert response.status_code == 422
    assert response.json()["detail"] == "notes.pdf: not a PDF"
    assert unbrander.jobs.jobs == {} and list(tmp_path.iterdir()) == []


def test_a_file_over_the_size_limit_is_refused_as_too_large(app, unbrander):
    unbrander.settings = unbrander.settings.model_copy(update={"unbrander_max_file_mb": 0})
    assert upload(app, [("prices.pdf", pdf())]).status_code == 413


def test_a_job_needs_a_project(app, unbrander, tmp_path):
    response = upload(app, [("prices.pdf", pdf())], fields={**FIELDS, "project": " "})
    assert response.status_code == 422
    assert unbrander.jobs.jobs == {} and list(tmp_path.iterdir()) == []


def test_without_a_database_unbrander_says_it_is_unavailable(app, unbrander):
    unbrander.jobs = None
    assert upload(app, [("prices.pdf", pdf())]).status_code == 503


def test_a_job_is_read_back_with_its_documents_and_audit_log(app, unbrander):
    job_id = upload(app, [("prices.pdf", pdf())]).json()["job_id"]
    with TestClient(app) as client:
        one = client.get(f"/admin/unbrander/jobs/{job_id}", headers=AUTH).json()
        listed = client.get("/admin/unbrander/jobs", headers=AUTH).json()["jobs"]
        missing = client.get("/admin/unbrander/jobs/nope", headers=AUTH)
    assert one["status"] == "RECEIVED" and len(one["documents"]) == 1
    assert [event["action"] for event in one["events"]] == ["upload"]
    assert [job["id"] for job in listed] == [job_id] and "documents" not in listed[0]
    assert missing.status_code == 404


def test_doctor_reports_ocr_and_the_job_store(app, unbrander):
    unbrander.ocr_problem = lambda: "no English language data in /usr/share/tessdata"
    with TestClient(app) as client:
        checks = client.get("/doctor", headers=AUTH).json()["checks"]
    assert checks["ocr"] == {"ok": False, "critical": False,
                             "detail": "no English language data in /usr/share/tessdata"}
    assert checks["job_store"]["ok"] is True
    assert checks["unbrander_worker"]["ok"] is None  # switched off


def test_an_upload_whose_audit_line_fails_still_reports_the_job(app, unbrander):
    async def down(event):
        raise RuntimeError("connection refused")
    unbrander.jobs.add_event = down
    response = upload(app, [("prices.pdf", pdf())])
    assert response.status_code == 202
    assert response.json()["job_id"] in unbrander.jobs.jobs


JPEG = b"\xff\xd8\xff"


def unbranded(app, unbrander, status=DocumentStatus.VERIFIED) -> str:
    """A job whose one document had 3 pages, page 2 dropped."""
    job_id = upload(app, [("Arista_SouthCal_Pricelist.pdf", pdf(3))]).json()["job_id"]
    document = unbrander.jobs.jobs[job_id].documents[0]
    document.status, document.doc_type, document.dropped_pages = status, "price_list", [2]
    unbrander.job_files.save_output(job_id, 1, pdf(2))
    return job_id


def get(app, path, headers=AUTH):
    with TestClient(app) as client:
        return client.get(f"/admin/unbrander/jobs/{path}", headers=headers)


def test_a_job_shows_each_documents_page_map(app, unbrander):
    job_id = unbranded(app, unbrander)
    document = get(app, job_id).json()["documents"][0]
    assert document["page_map"] == {"1": 1, "2": None, "3": 2}


def test_pages_are_served_as_jpegs_by_source_page_number(app, unbrander):
    job_id = unbranded(app, unbrander)
    source = get(app, f"{job_id}/documents/1/pages/3.jpg")
    output = get(app, f"{job_id}/documents/1/pages/3.jpg?version=output")
    assert source.status_code == output.status_code == 200
    assert source.content.startswith(JPEG) and output.content.startswith(JPEG)
    assert source.headers["content-type"] == "image/jpeg"
    assert source.headers["cache-control"] == "private, max-age=3600"


def test_a_dropped_or_missing_page_is_not_found(app, unbrander):
    job_id = unbranded(app, unbrander)
    dropped = get(app, f"{job_id}/documents/1/pages/2.jpg?version=output")
    assert (dropped.status_code, dropped.json()["detail"]) == (404, "page 2 was dropped")
    assert get(app, f"{job_id}/documents/1/pages/4.jpg").status_code == 404
    assert get(app, f"{job_id}/documents/2/pages/1.jpg").status_code == 404
    assert get(app, "nope/documents/1/pages/1.jpg").status_code == 404


def test_output_is_not_found_before_the_document_is_unbranded(app, unbrander):
    job_id = upload(app, [("prices.pdf", pdf())]).json()["job_id"]
    assert get(app, f"{job_id}/documents/1/pages/1.jpg?version=output").status_code == 404
    assert get(app, f"{job_id}/documents/1/output.pdf").status_code == 404
    assert get(app, f"{job_id}/documents/1/pages/1.jpg").status_code == 200


def test_the_cleaned_pdf_downloads_under_its_filed_name(app, unbrander):
    job_id = unbranded(app, unbrander)
    response = get(app, f"{job_id}/documents/1/output.pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert response.headers["content-disposition"] == 'attachment; filename="Price List.pdf"'


def test_a_blocked_document_still_downloads_for_review(app, unbrander):
    job_id = unbranded(app, unbrander, status=DocumentStatus.BLOCKED)
    assert get(app, f"{job_id}/documents/1/output.pdf").status_code == 200


def test_a_realtor_cannot_see_pages_or_download(app, unbrander):
    job_id = unbranded(app, unbrander)
    unbrander.auth = FakeAuthVerifier()
    assert get(app, f"{job_id}/documents/1/pages/1.jpg").status_code == 403
    assert get(app, f"{job_id}/documents/1/output.pdf").status_code == 403


def test_the_mark_preview_is_a_jpeg_for_admins_only(app, unbrander):
    brand = {"mark_words": [{"text": "AURA", "colour": "#0E1A24"}], "size": 9}
    with TestClient(app) as client:
        preview = client.post("/admin/unbrander/mark-preview", json=brand, headers=AUTH)
        bad = client.post("/admin/unbrander/mark-preview",
                          json={"mark_words": [{"text": "A1", "colour": "red"}]}, headers=AUTH)
        unbrander.auth = FakeAuthVerifier()
        realtor = client.post("/admin/unbrander/mark-preview", json=brand, headers=AUTH)
    assert preview.status_code == 200 and preview.content.startswith(JPEG)
    assert bad.status_code == 422 and realtor.status_code == 403


def post(app, path, headers=AUTH):
    with TestClient(app) as client:
        return client.post(f"/admin/unbrander/jobs/{path}", headers=headers)


def test_an_upload_waits_for_filing_unless_asked_to_file_when_done(app, unbrander):
    can_file(unbrander)
    later = upload(app, [("prices.pdf", pdf())]).json()["job_id"]
    now = upload(app, [("prices.pdf", pdf())], fields={**FIELDS, "file_when_done": "true"}).json()["job_id"]
    assert not unbrander.jobs.jobs[later].file_when_done
    assert unbrander.jobs.jobs[now].file_when_done


def test_asking_to_file_when_done_without_drive_is_refused_before_anything_is_kept(app, unbrander,
                                                                                    tmp_path):
    response = upload(app, [("prices.pdf", pdf())], fields={**FIELDS, "file_when_done": "true"})
    assert response.status_code == 422 and "Drive is not set up" in response.json()["detail"]
    assert unbrander.jobs.jobs == {} and list(tmp_path.iterdir()) == []


def test_an_unbranded_job_is_sent_to_filing_and_the_request_is_logged(app, unbrander):
    can_file(unbrander)
    job_id = unbranded(app, unbrander)
    unbrander.jobs.jobs[job_id].status = JobStatus.UNBRANDED
    response = post(app, f"{job_id}/file")
    assert response.status_code == 202 and response.json()["status"] == "FILING"
    assert unbrander.jobs.jobs[job_id].status is JobStatus.FILING
    assert [(e.actor, e.action, e.result) for e in unbrander.jobs.event_log][-1] == (
        "sudhanshu", "file", "requested")


def test_only_an_unbranded_job_can_be_filed(app, unbrander):
    can_file(unbrander)
    job_id = unbranded(app, unbrander)  # still RECEIVED
    response = post(app, f"{job_id}/file")
    assert response.status_code == 409 and "RECEIVED" in response.json()["detail"]
    assert post(app, "nope/file").status_code == 404


def test_filing_without_drive_is_unavailable_and_a_realtor_cannot_file(app, unbrander):
    job_id = unbranded(app, unbrander)
    unbrander.jobs.jobs[job_id].status = JobStatus.UNBRANDED
    assert post(app, f"{job_id}/file").status_code == 503
    can_file(unbrander)
    unbrander.auth = FakeAuthVerifier()
    assert post(app, f"{job_id}/file").status_code == 403
    assert unbrander.jobs.jobs[job_id].status is JobStatus.UNBRANDED


def test_the_upload_limits_come_from_the_settings(app, unbrander):
    unbrander.settings = unbrander.settings.model_copy(update={"unbrander_max_file_mb": 150})
    with TestClient(app) as client:
        limits = client.get("/admin/unbrander/limits", headers=AUTH)
        unbrander.auth = FakeAuthVerifier()
        realtor = client.get("/admin/unbrander/limits", headers=AUTH)
    assert limits.json() == {"max_files": 10, "max_file_mb": 150, "max_pages": 60,
                             "can_file": False}
    assert realtor.status_code == 403


def test_the_limits_say_when_filing_is_possible(app, unbrander):
    can_file(unbrander)
    with TestClient(app) as client:
        assert client.get("/admin/unbrander/limits", headers=AUTH).json()["can_file"] is True


def test_filing_is_refused_while_the_worker_is_off(app, unbrander):
    can_file(unbrander)
    unbrander.worker = None
    job_id = unbranded(app, unbrander)
    unbrander.jobs.jobs[job_id].status = JobStatus.UNBRANDED
    response = post(app, f"{job_id}/file")
    assert response.status_code == 503 and "worker is switched off" in response.json()["detail"]
    later = upload(app, [("prices.pdf", pdf())], fields={**FIELDS, "file_when_done": "true"})
    assert later.status_code == 422


def test_a_job_whose_files_were_evicted_is_not_sent_to_filing(app, unbrander):
    can_file(unbrander)
    job_id = unbranded(app, unbrander)
    unbrander.jobs.jobs[job_id].status = JobStatus.UNBRANDED
    unbrander.job_files.evict(job_id)
    response = post(app, f"{job_id}/file")
    assert response.status_code == 410 and "removed after 30 days" in response.json()["detail"]
    assert unbrander.jobs.jobs[job_id].status is JobStatus.UNBRANDED


def test_a_second_file_request_is_refused_and_logged_once(app, unbrander):
    can_file(unbrander)
    job_id = unbranded(app, unbrander)
    unbrander.jobs.jobs[job_id].status = JobStatus.UNBRANDED
    assert post(app, f"{job_id}/file").status_code == 202
    assert post(app, f"{job_id}/file").status_code == 409
    assert [e.action for e in unbrander.jobs.event_log].count("file") == 1


def test_the_summary_counts_jobs_since_the_start_the_client_gives(app, unbrander):
    upload(app, [("prices.pdf", pdf())])
    with TestClient(app) as client:
        now = client.get("/admin/unbrander/summary", headers=AUTH,
                         params={"since": "2026-10-01T00:00:00-04:00"})
        later = client.get("/admin/unbrander/summary", headers=AUTH,
                           params={"since": "2099-01-01T00:00:00Z"})
        unbrander.auth = FakeAuthVerifier()
        realtor = client.get("/admin/unbrander/summary", headers=AUTH)
    assert now.json() == {"to_review": 0, "working": 1, "jobs_since": 1, "pages_cleaned_since": 0}
    assert later.json()["jobs_since"] == 0 and later.json()["working"] == 1
    assert realtor.status_code == 403


def test_the_summary_without_a_database_is_unavailable(app, unbrander):
    unbrander.jobs = None
    with TestClient(app) as client:
        assert client.get("/admin/unbrander/summary", headers=AUTH).status_code == 503


def test_jobs_are_listed_by_several_statuses_with_their_documents_when_asked(app, unbrander):
    first = upload(app, [("prices.pdf", pdf())]).json()["job_id"]
    second = upload(app, [("plans.pdf", pdf(3))]).json()["job_id"]
    unbrander.jobs.jobs[second].status = JobStatus.UNBRANDED
    with TestClient(app) as client:
        both = client.get("/admin/unbrander/jobs", headers=AUTH,
                          params={"status": ["RECEIVED", "UNBRANDED"], "documents": "true"}).json()
        ready = client.get("/admin/unbrander/jobs", headers=AUTH, params={"status": "UNBRANDED"}).json()
    assert [job["id"] for job in both["jobs"]] == [second, first]
    assert [d["page_count"] for d in both["documents"][second]] == [3]
    assert [job["id"] for job in ready["jobs"]] == [second] and ready["documents"] is None
