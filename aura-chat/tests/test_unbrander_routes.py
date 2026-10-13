"""The admin API for Unbrander jobs, over the fake job store and the real intake check."""

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.files import JobFiles
from app.domain import Claims, Organization, Role
from tests.fakes import FakeAuthVerifier, FakeJobStore

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
    return services


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
