import pytest
from pydantic import ValidationError

from app.capabilities.unbrander.domain import (
    ENDED,
    DocumentStatus,
    JobDocument,
    JobStatus,
    NewDocument,
    NewJob,
    PageSort,
    Sorting,
    document_type,
    project_folders,
    subfolder,
)
from app.domain import Organization


def sorting(*pages: tuple[str, bool]) -> Sorting:
    return Sorting(pages=[PageSort(page=number, kind=kind, keep=keep, why="")
                          for number, (kind, keep) in enumerate(pages, start=1)],
                   terms=[])


def new_job(**overrides) -> NewJob:
    fields = {"uploader": "admin", "project": "SouthCal", "builder": "Arista Homes",
              "city": "Vaughan", "organization": Organization(), "dry_run": True,
              "documents": [NewDocument(filename="plans.pdf", sha256="ab", page_count=3)]}
    return NewJob(**(fields | overrides))


def test_the_document_type_is_the_most_common_kept_page_kind():
    assert document_type(sorting(("marketing", False), ("marketing", False),
                                 ("price_list", True), ("price_list", True),
                                 ("site_plan", True))) == "price_list"


def test_elevations_count_as_floor_plans():
    assert document_type(sorting(("elevation", True), ("elevation", True),
                                 ("price_list", True))) == "floor_plan"


def test_a_document_with_nothing_kept_has_no_type():
    assert document_type(sorting(("marketing", False))) is None


def test_a_job_needs_a_project_a_builder_a_city_and_a_document():
    for field in ("project", "builder", "city"):
        with pytest.raises(ValidationError):
            new_job(**{field: ""})
    with pytest.raises(ValidationError):
        new_job(documents=[])


def test_a_job_ends_filed_or_failed_and_nowhere_else():
    assert ENDED == {JobStatus.FILED_PRIVATE, JobStatus.FAILED}


def filed(*types: str) -> list[JobDocument]:
    return [JobDocument(id=f"d{i}", job_id="j", position=i, filename=f"{i}.pdf", sha256="",
                        page_count=1, status=DocumentStatus.VERIFIED, doc_type=kind)
            for i, kind in enumerate(types, start=1)]


def test_floor_plans_get_their_own_folder_only_when_there_are_several():
    several = filed("floor_plan", "floor_plan", "price_list")
    assert [subfolder(document, several) for document in several] == [
        "Floor Plans", "Floor Plans", None]
    single = filed("floor_plan", "site_plan")
    assert [subfolder(document, single) for document in single] == [None, None]


def test_a_project_is_filed_under_province_city_and_project_with_builder():
    job = new_job()
    assert project_folders(job) == ["Ontario", "Vaughan", "SouthCal - Arista Homes"]
