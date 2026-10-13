import pytest

from app.capabilities.unbrander.domain import Screening
from app.capabilities.unbrander.intake import UploadRejected, check_upload
from tests.fakes import FakePdfInspector

PDF = b"%PDF-1.7 builder brochure"


def check(data: bytes = PDF, screening: Screening | None = None, *, max_mb: int = 50,
          max_pages: int = 60) -> Screening:
    inspector = FakePdfInspector(screenings={
        data: screening or Screening(readable=True, page_count=12)})
    return check_upload("brochure.pdf", data, inspector=inspector, max_mb=max_mb,
                        max_pages=max_pages)


def rejected(**arguments) -> UploadRejected:
    with pytest.raises(UploadRejected) as caught:
        check(**arguments)
    return caught.value


def test_a_clean_pdf_passes_with_its_page_count():
    assert check().page_count == 12


def test_a_file_over_the_size_limit_is_refused_as_too_large():
    error = rejected(data=b"%PDF-" + b"x" * (1024 * 1024), max_mb=1)
    assert error.too_large and "larger than 1 MB" in str(error)


def test_a_renamed_file_is_refused_by_its_content():
    assert str(rejected(data=b"PK\x03\x04 a docx")) == "brochure.pdf: not a PDF"


def test_bytes_that_do_not_open_are_refused():
    assert "could not be opened" in str(rejected(screening=Screening(readable=False)))


def test_a_password_protected_pdf_is_refused():
    assert "password" in str(rejected(screening=Screening(readable=True, encrypted=True)))


def test_too_many_pages_is_refused():
    error = rejected(screening=Screening(readable=True, page_count=61))
    assert "more than 60 pages" in str(error) and not error.too_large


def test_active_content_is_refused_and_named():
    error = rejected(screening=Screening(readable=True, page_count=2, javascript=True,
                                         launch_action=True))
    assert str(error) == "brochure.pdf: contains JavaScript, launch actions"
