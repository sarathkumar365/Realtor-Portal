"""verify() on hand-built facts. No PDF, no pymupdf, no tesseract.

The regressions at the bottom are the leaks and false alarms the spike and the
Claude-chat field reports actually hit.
"""

from app.capabilities.unbrander.domain import (
    Check,
    HitList,
    PageFacts,
    Paint,
    PdfFacts,
    Severity,
    Word,
)
from app.capabilities.unbrander.verify import verify

HITS = HitList(builder="Arista Homes", project="SouthCal", short_forms=["AH"])
CLEAN_OCR = {"normal": "Lot 12 Model A", "inverted": "", "light": ""}


def page(*words: str, number: int = 1, ocr: dict | None = None, paint=(), size=(612, 792)):
    ws = [Word(text=w, bbox=(10.0 * i, 10, 10.0 * i + 9, 20)) for i, w in enumerate(words)]
    return PageFacts(number=number, width=size[0], height=size[1], words=ws,
                     paint=list(paint), ocr=CLEAN_OCR if ocr is None else ocr)


def facts(*pages: PageFacts, **kw) -> PdfFacts:
    return PdfFacts(pages=list(pages), **kw)


SOURCE = facts(page("SouthCal", "by", "Arista", "Homes", "Lot", "12", "Model", "A", "$1,234,567",
                    "includes", "9'", "ceilings", "Call", "905-555-0100"))


def checks(report, check: Check):
    return [f for f in report.findings if f.check is check]


def test_a_clean_output_passes():
    out = facts(page("Lot", "12", "Model", "A", "$1,234,567", "includes", "9'", "ceilings"))
    report = verify(SOURCE, out, HITS)
    assert report.findings == []
    assert report.passed


def test_text_sweep_finds_names_and_their_spaced_variants():
    out = facts(page("South", "Cal", "Lot", "12"), page("S", "O", "U", "T", "H", "C", "A", "L",
                                                        number=2),
                page("arista-homes", number=3))
    found = checks(verify(SOURCE, out, HITS), Check.TEXT_SWEEP)
    assert {f.page for f in found} == {1, 2, 3}
    assert all(f.severity is Severity.RETRY for f in found)
    assert found[0].bbox is not None


def test_text_sweep_finds_contact_details():
    out = facts(page("Visit", "www.southcalhomes.ca", "or", "905-555-0100", "sales@arista.com"))
    found = checks(verify(SOURCE, out, HITS), Check.TEXT_SWEEP)
    details = " ".join(f.detail for f in found)
    assert "url" in details and "phone" in details and "email" in details
    generic = [f for f in found if "'SouthCal'" not in f.detail and "'Arista" not in f.detail]
    assert generic and all(f.severity is Severity.FLAG for f in generic)


def test_a_builder_url_is_a_retry_through_the_hit_list():
    found = checks(verify(SOURCE, facts(page("www.aristahomes.com")), HITS), Check.TEXT_SWEEP)
    assert any(f.severity is Severity.RETRY and "'Arista Homes'" in f.detail for f in found)


def test_short_forms_match_only_as_a_whole_case_sensitive_word():
    out = facts(page("AH", "ahead", "Ah", "Lot"))
    found = checks(verify(SOURCE, out, HITS), Check.TEXT_SWEEP)
    assert [f.detail for f in found] == ["'AH' in the text layer: 'AH'"]


def test_a_term_with_no_letters_or_digits_is_ignored():
    hits = HitList(builder="Arista Homes", project="SouthCal", extras=["@", " — ", ""])
    assert hits.terms() == ["Arista Homes", "SouthCal"]
    assert verify(SOURCE, facts(page("Lot", "12"), object_text="<</A 1>>"), hits).findings == []


def test_raw_bytes_finds_names_inside_pdf_objects():
    out = facts(page("Lot"), object_text="<</Type/OCG/Name(SouthCal_DT 2001)>>")
    found = checks(verify(SOURCE, out, HITS), Check.RAW_BYTES)
    assert len(found) == 1 and "SouthCal_DT" in found[0].detail


def test_raw_bytes_matches_names_run_together():
    out = facts(page("Lot"), object_text="/XObject<</ARISTAHOMESLOGO 9 0 R>>")
    assert checks(verify(SOURCE, out, HITS), Check.RAW_BYTES)


def test_ocr_sweep_catches_light_ink_and_misreads():
    ocr = {"normal": "Lot 12", "inverted": "", "light": "S0UTHCAL"}
    found = checks(verify(SOURCE, facts(page("Lot", ocr=ocr)), HITS), Check.OCR_SWEEP)
    assert len(found) == 1 and "light" in found[0].detail


def test_ocr_sweep_tolerates_one_edit_on_long_names():
    for misread in ("Arista Hames", "Arista Hornes", "Arlsta Homes"):
        ocr = {"normal": misread, "inverted": "", "light": ""}
        assert checks(verify(SOURCE, facts(page("Lot", ocr=ocr)), HITS), Check.OCR_SWEEP), misread


def test_ocr_not_run_blocks():
    found = checks(verify(SOURCE, facts(page("Lot", ocr={})), HITS), Check.OCR_SWEEP)
    assert found[0].severity is Severity.BLOCK
    assert not verify(SOURCE, facts(page("Lot", ocr={})), HITS).passed


def test_a_changed_number_blocks():
    report = verify(SOURCE, facts(page("Lot", "12", "$1,243,567")), HITS)
    found = checks(report, Check.NUMBERS)
    assert [f.detail for f in found] == ["'1,243,567' is not in the source"]
    assert not report.passed


def test_numbers_compare_by_value_not_format():
    out = facts(page("1234567", "12.0", "012"))
    assert checks(verify(SOURCE, out, HITS), Check.NUMBERS) == []


def test_an_invented_word_is_flagged_not_blocked():
    report = verify(SOURCE, facts(page("Lot", "12", "luxurious", "vendor", "A", "U", "R", "A")),
                    HITS)
    found = checks(report, Check.PROVENANCE)
    assert len(found) == 1 and "'luxurious'" in found[0].detail
    assert found[0].severity is Severity.FLAG
    assert report.passed


def test_ligatures_are_not_new_words():
    src = facts(page("reflects", "efficiency"))
    out = facts(page("re\ufb02ects", "e\ufb03ciency"))
    assert checks(verify(src, out, HITS), Check.PROVENANCE) == []


def test_metadata_must_be_empty():
    out = facts(page("Lot"), metadata={"author": "Arista"}, xmp="<x:xmpmeta/>", links=2)
    found = checks(verify(SOURCE, out, HITS), Check.METADATA)
    assert len(found) == 1
    assert "author='Arista'" in found[0].detail and "2 links" in found[0].detail


def test_an_opaque_box_over_an_image_is_a_cover_up():
    paint = [Paint(kind="image", bbox=(0, 0, 100, 50)),
             Paint(kind="path", bbox=(-1, -1, 101, 51), opaque=True)]
    found = checks(verify(SOURCE, facts(page("Lot", paint=paint)), HITS), Check.COVER_UP)
    assert len(found) == 1 and "image" in found[0].detail


def test_a_panel_under_text_or_a_tint_over_a_photo_is_design():
    paint = [Paint(kind="path", bbox=(0, 0, 612, 100), opaque=True),
             Paint(kind="text", bbox=(10, 10, 90, 20)),
             Paint(kind="image", bbox=(0, 200, 612, 500)),
             Paint(kind="path", bbox=(0, 200, 612, 500), opaque=False)]
    assert checks(verify(SOURCE, facts(page("Lot", paint=paint)), HITS), Check.COVER_UP) == []


def test_undeclared_dropped_pages_are_flagged():
    src = facts(page("Lot"), page("Lot", number=2))
    found = checks(verify(src, facts(page("Lot")), HITS), Check.PAGES)
    assert "none declared" in found[0].detail and found[0].severity is Severity.FLAG
    assert checks(verify(src, facts(page("Lot")), HITS, dropped_pages=[2]), Check.PAGES) == []


def test_a_resized_page_is_flagged():
    found = checks(verify(SOURCE, facts(page("Lot", size=(612, 700))), HITS), Check.PAGES)
    assert len(found) == 1 and found[0].page == 1


# Regressions from the spike and the field reports.

def test_inc_does_not_match_include():
    hits = HitList(builder="Arista Homes Inc", project="SouthCal", extras=["Inc"])
    out = facts(page("Lot", "includes", "9'", "ceilings"))
    assert checks(verify(SOURCE, out, hits), Check.TEXT_SWEEP) == []
