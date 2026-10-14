import pytest
from pydantic import ValidationError

from app.capabilities.unbrander.domain import (
    ENDED,
    Check,
    DocumentStatus,
    Finding,
    JobDocument,
    JobStatus,
    NewDocument,
    NewJob,
    PageSort,
    Sorting,
    Severity,
    document_type,
    file_names,
    in_source_pages,
    page_map,
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


def test_a_job_rests_unbranded_filed_or_failed_and_nowhere_else():
    assert ENDED == {JobStatus.UNBRANDED, JobStatus.FILED_PRIVATE, JobStatus.FAILED}


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


def test_the_page_map_pairs_each_source_page_with_its_output_page():
    assert page_map(5, [2, 4]) == {1: 1, 2: None, 3: 2, 4: None, 5: 3}
    assert page_map(2, []) == {1: 1, 2: 2}


def finding(check: Check, page: int | None) -> Finding:
    return Finding(check=check, severity=Severity.FLAG, detail="", page=page)


def test_findings_are_stored_in_source_page_numbers():
    # Source pages 1-5, 2 dropped: output page 2 is source page 3. verify() reads
    # the output; the judge already speaks in source pages.
    converted = in_source_pages(
        [finding(Check.TEXT_SWEEP, 2), finding(Check.DAMAGE, 4), finding(Check.VISUAL, 3),
         finding(Check.METADATA, None), finding(Check.PAGES, 9)],
        page_count=5, dropped_pages=[2])
    assert [item.page for item in converted] == [3, 5, 3, None, None]


def test_a_document_reports_its_page_map():
    document = filed("price_list")[0].model_copy(update={"page_count": 3, "dropped_pages": [1]})
    assert document.model_dump(mode="json")["page_map"] == {"1": None, "2": 1, "3": 2}


def test_filed_names_come_from_the_document_type_never_the_upload():
    documents = filed("price_list", "floor_plan", "floor_plan", None)
    assert list(file_names(documents).values()) == [
        "Price List.pdf", "Floor Plan 1.pdf", "Floor Plan 2.pdf", "Document.pdf"]
