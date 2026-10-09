"""The pymupdf edit adapter, on tiny PDFs built inside each test. No binaries in git."""

import shutil

import pymupdf
import pytest

from app.capabilities.unbrander.adapters.pdf_edit_pymupdf import PyMuPdfEditor
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.domain import (
    Brief,
    HitList,
    MarkPosition,
    PageSort,
    RedactTerms,
    Sorting,
    ToolRejected,
    Word,
    missing,
)
from app.capabilities.unbrander.tools import Toolbox, number_elements
from app.capabilities.unbrander.unbrand import unbrand_document
from app.capabilities.unbrander.verify import verify
from tests.fakes import FakeUnbrandModels

has_tesseract = shutil.which("tesseract") is not None


def build(draw, pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        draw(doc, doc.new_page(width=612, height=792))
    return doc.tobytes()


def logo_pixmap() -> "pymupdf.Pixmap":
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
    pixmap.set_rect(pixmap.irect, (200, 30, 30))
    return pixmap


def page_text(pdf: bytes, n: int = 0) -> str:
    with pymupdf.open(stream=pdf) as doc:
        return doc[n].get_text()


def test_redact_text_removes_the_word_from_text_and_bytes_and_keeps_line_art():
    def draw(doc, page):
        page.insert_text((72, 100), "Living SouthCal Room")
        page.draw_line((60, 103), (400, 103), color=(0, 0, 0), width=1)
    session = PyMuPdfEditor().open(build(draw))
    target = next(w for w in session.words(1) if w.text == "SouthCal")
    session.redact_text(1, [target.bbox])
    out = session.save(drop=[], mark=None)
    assert "SouthCal" not in page_text(out)
    assert "Living" in page_text(out) and "Room" in page_text(out)
    assert b"SouthCal" not in pymupdf.open(stream=out).tobytes(expand=255)
    with pymupdf.open(stream=out) as doc:
        assert len(doc[0].get_drawings()) == 1


def test_redact_text_spares_the_line_below_when_leading_is_tight():
    """The brochure's "BUY AN ARISTA / STAR® CERTIFIED": the line boxes overlap, and
    redacting the full box of ARISTA also took the ® and CERTI under it."""
    def draw(doc, page):
        page.insert_text((72, 100), "BUY AN ARISTA", fontsize=20)
        page.insert_text((72, 120), "STAR CERTIFIED HOME", fontsize=20)  # set solid
    session = PyMuPdfEditor().open(build(draw))
    words = {w.text: w.bbox for w in session.words(1)}
    assert words["ARISTA"][3] > words["CERTIFIED"][1]  # the boxes really overlap
    session.redact_text(1, [words["ARISTA"]])
    assert [w.text for w in session.words(1)] == ["BUY", "AN", "STAR", "CERTIFIED", "HOME"]


def test_redact_area_clears_image_pixels_and_reports_words_lost():
    def draw(doc, page):
        page.insert_image(pymupdf.Rect(400, 20, 560, 100), pixmap=logo_pixmap())
        page.insert_text((420, 120), "Presentation Centre")
        page.insert_text((72, 400), "Lot 12")
    session = PyMuPdfEditor().open(build(draw))
    lost = session.redact_area(1, (380, 0, 612, 140))
    assert [w.text for w in lost] == ["Presentation", "Centre"]
    with pymupdf.open(stream=session.save(drop=[], mark=None)) as doc:
        pixmap = doc[0].get_pixmap(clip=pymupdf.Rect(450, 40, 500, 80))
        assert set(pixmap.samples) == {255}  # white: the red logo is gone
        assert "Lot 12" in doc[0].get_text()


def test_a_logo_drawn_in_parts_is_one_element_and_a_plan_is_left_whole():
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(400, 700, 420, 720), color=None, fill=(0, 0.5, 0.5))
        page.draw_rect(pymupdf.Rect(424, 700, 470, 720), color=None, fill=(0, 0.5, 0.5))
        page.draw_rect(pymupdf.Rect(50, 100, 550, 600), color=(0, 0, 0), width=2)
        page.insert_image(pymupdf.Rect(20, 20, 100, 60), pixmap=logo_pixmap())
    session = PyMuPdfEditor().open(build(draw))
    found = {(ref.kind, tuple(round(value) for value in ref.bbox)) for ref in session.elements(1)}
    assert ("coloured shapes", (400, 700, 470, 720)) in found
    assert ("image", (20, 20, 100, 60)) in found


def test_redact_area_leaves_a_panel_it_only_touches():
    """Run 6: with REMOVE_IF_TOUCHED, a logo's box took the panel behind it."""
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(0, 650, 612, 792), color=None, fill=(0, 0.5, 0.5))
        page.draw_rect(pymupdf.Rect(400, 700, 470, 720), color=None, fill=(1, 1, 1))
    session = PyMuPdfEditor().open(build(draw))
    session.redact_area(1, (399, 699, 471, 721))
    with pymupdf.open(stream=session.save(drop=[], mark=None)) as doc:
        rects = [tuple(round(v) for v in d["rect"]) for d in doc[0].get_drawings()]
    assert (0, 650, 612, 792) in rects and (400, 700, 470, 720) not in rects


def test_redact_area_over_a_transparent_image_leaves_no_black():
    """Run 6, page 3: an image emptied by pymupdf's delete_image is a transparent
    stand-in, and blanking part of it by pixels painted it black."""
    def draw(doc, page):
        xref = page.insert_image(pymupdf.Rect(100, 100, 300, 200), pixmap=logo_pixmap())
        page.delete_image(xref)
    session = PyMuPdfEditor().open(build(draw))
    session.redact_area(1, (90, 90, 200, 210))  # part of the image
    with pymupdf.open(stream=session.save(drop=[], mark=None)) as doc:
        pixmap = doc[0].get_pixmap(clip=pymupdf.Rect(100, 100, 300, 200))
    assert min(pixmap.samples) > 200  # white, not black


def test_a_numbered_render_is_the_same_size_as_a_plain_one():
    session = PyMuPdfEditor().open(build(lambda doc, page: page.insert_text((72, 72), "x")))
    plain = pymupdf.Pixmap(session.render(1, 100))
    numbered = pymupdf.Pixmap(session.render(1, 100, marks=[(1, (60, 60, 120, 90))]))
    assert (plain.width, plain.height) == (numbered.width, numbered.height)
    assert plain.samples != numbered.samples


def test_save_drops_pages_and_marks_every_kept_page_in_the_same_place():
    pdf = build(lambda d, p: p.insert_text((72, 72), f"Page {p.number + 1}"), pages=3)
    out = PyMuPdfEditor().open(pdf).save(drop=[2], mark=MarkPosition.BOTTOM_RIGHT)
    with pymupdf.open(stream=out) as doc:
        assert [p.get_text().split()[:2] for p in doc] == [["Page", "1"], ["Page", "3"]]
        spots = [p.search_for("A")[-1] for p in doc]
        assert spots[0] == spots[1]
        assert spots[0].x0 > 450 and spots[0].y1 > 740


def test_save_keeps_the_invisible_ocr_layer_of_a_scan():
    def draw(doc, page):
        page.insert_text((72, 100), "The Aspen $1,234,990", render_mode=3)
    out = PyMuPdfEditor().open(build(draw)).save(drop=[], mark=None)
    assert "$1,234,990" in page_text(out)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_mark_sits_bottom_right_as_a_rotated_page_is_seen(rotation):
    pdf = build(lambda d, p: p.set_rotation(rotation))
    out = PyMuPdfEditor().open(pdf).save(drop=[], mark=MarkPosition.BOTTOM_RIGHT)
    with pymupdf.open(stream=out) as doc:
        page = doc[0]
        seen = page.search_for("Y")[-1] * page.rotation_matrix  # the last letter
        assert seen.x1 > page.rect.width - 60 and seen.y1 > page.rect.height - 60


def test_save_strips_metadata_everywhere():
    def draw(doc, page):
        doc.set_metadata({"author": "Arista Homes", "title": "SouthCal"})
        doc.set_xml_metadata("<x>SouthCal</x>")
        doc.add_ocg("SouthCal_DT 2001")
        page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(0, 0, 50, 50),
                          "uri": "https://aristahomes.com"})
        page.add_text_annot((100, 100), "SouthCal")
        xref = page.insert_image(pymupdf.Rect(20, 20, 100, 60), pixmap=logo_pixmap())
        meta = doc.get_new_xref()
        doc.update_object(meta, "<</Type/Metadata/Subtype/XML>>")
        doc.update_stream(meta, b"<rdf:li>/Volumes/ARISTA/SouthCal_DT</rdf:li>")
        doc.xref_set_key(xref, "Metadata", f"{meta} 0 R")
    out = PyMuPdfEditor().open(build(draw)).save(drop=[], mark=None)
    facts = PyMuPdfInspector().inspect(out, ocr=False)
    assert facts.metadata.keys() <= {"producer", "creator"}  # pymupdf may stamp itself
    assert "SouthCal" not in facts.xmp
    assert (facts.annotations, facts.links, facts.embedded_files) == (0, 0, 0)
    assert "SouthCal" not in facts.object_text and "ARISTA" not in facts.object_text


def test_toolbox_output_passes_verify():
    """End to end: tools, save, then the real inspector and verify()."""
    def draw(doc, page):
        doc.set_metadata({"author": "Arista Homes"})
        page.insert_text((72, 100), "SouthCal by Arista Homes", fontsize=24)
        if page.number == 0:  # a priced page is never dropped
            page.insert_text((72, 200), "The Aspen  1,850 sq ft  $1,234,990", fontsize=14)
    pdf = build(draw, pages=2)
    hits = HitList(builder="Arista Homes", project="SouthCal")
    inspector = PyMuPdfInspector()
    source = inspector.inspect(pdf, ocr=False)
    session = PyMuPdfEditor().open(pdf)
    tb = Toolbox(session, source, hits, {page: number_elements(session, page) for page in (1, 2)})
    tb.redact_terms(["SouthCal", "Arista Homes"])
    tb.drop_page(2, "duplicate")
    tb.add_mark("bottom_right")
    done = tb.finish()
    report = verify(source, inspector.inspect(done.pdf, ocr=has_tesseract), hits,
                    dropped_pages=done.dropped_pages)
    assert [f for f in report.findings if f.severity != "flag"] == []
    assert report.passed


@pytest.mark.skipif(not has_tesseract, reason="the unbrand step always runs verify with OCR")
async def test_the_unbrand_step_on_a_real_pdf_replays_from_the_source_each_round():
    """Two rounds on real pymupdf: the repair's action lands on a fresh copy of the
    source together with the sort's, and the dropped page shifts nothing."""
    def draw(doc, page):
        page.insert_text((72, 100), f"SouthCal page {page.number + 1} Arista Homes", fontsize=14)
    pdf = build(draw, pages=3)
    hits = HitList(builder="Arista Homes", project="SouthCal")
    sorting = Sorting(pages=[PageSort(page=1, kind="marketing", keep=False, why="cover"),
                             PageSort(page=2, kind="floor_plan", keep=True, why="plan"),
                             PageSort(page=3, kind="floor_plan", keep=True, why="plan")],
                      terms=["SouthCal"])
    fix = RedactTerms(terms=["Arista Homes"], why="builder")
    models = FakeUnbrandModels(sorting, repair={2: [fix], 3: [fix]})
    inspector = PyMuPdfInspector()
    done = await unbrand_document(pdf, Brief(hits=hits, page_count=3), editor=PyMuPdfEditor(),
                                  inspector=inspector, models=models,
                                  max_repair_rounds=1)
    assert done.rounds == 2 and done.dropped_pages == [1]
    assert {p for p, _ in models.repaired} == {2, 3}
    assert [page_text(done.pdf, i).split()[:2] for i in (0, 1)] == [["page", "2"], ["page", "3"]]
    assert done.report.passed


def test_words_that_only_moved_a_hair_are_not_lost():
    """Run 7: rewriting the content moved every word by about 1e-4 points, and a
    logo's removal reported a floor plan's labels as removed."""
    before = [Word(text="LOW", bbox=(665.16839, 544.97387, 672.65686, 549.54760)),
              Word(text="LOW", bbox=(652.24243, 384.97323, 659.73083, 389.54696)),
              Word(text="ARISTA", bbox=(30, 770, 100, 790))]
    after = [Word(text="LOW", bbox=(665.16839, 544.97393, 672.65686, 549.54766)),
             Word(text="LOW", bbox=(652.24243, 384.97326, 659.73083, 389.54699))]
    assert [word.text for word in missing(before, after)] == ["ARISTA"]


def test_a_coloured_watermark_beside_a_black_plan_is_its_own_element():
    """Bright Side floor plans: a pale flower a few points from the plan joined it."""
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(50, 100, 400, 600), color=(0, 0, 0), width=2)
        page.draw_circle(pymupdf.Point(150, 680), 70, color=(0.95, 0.6, 0.6), width=1)
    session = PyMuPdfEditor().open(build(draw))
    found = {(ref.kind, tuple(round(value) for value in ref.bbox)) for ref in session.elements(1)}
    assert ("coloured shapes", (80, 610, 220, 750)) in found
    assert ("shapes", (50, 100, 400, 600)) in found


def test_a_watermark_over_plan_lines_covers_the_plan_group_and_is_refused():
    """Removing the watermark would take the plan's lines wholly inside it."""
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(50, 100, 450, 500), color=(0, 0, 0), width=2)
        page.draw_line(pymupdf.Point(200, 300), pymupdf.Point(260, 300), color=(0, 0, 0))
        page.draw_circle(pymupdf.Point(230, 300), 60, color=(0.95, 0.6, 0.6), width=1)
    pdf = build(draw)
    session = PyMuPdfEditor().open(pdf)
    covered = session.groups_covered(1, (169, 239, 291, 361))
    assert ("shapes", (50, 100, 450, 500)) in {
        (group.kind, tuple(round(value) for value in group.bbox)) for group in covered}
    source = PyMuPdfInspector().inspect(pdf, ocr=False)
    numbering = {1: number_elements(session, 1)}
    tb = Toolbox(session, source, HitList(builder="Arista Homes", project="SouthCal"), numbering)
    [number] = [number for number, ref in numbering[1].items()
                if ref.kind == "coloured shapes"]
    with pytest.raises(ToolRejected, match="page's own drawing"):
        tb.remove_element(1, number)


def test_a_whole_image_beside_part_of_a_transparent_one_is_refused_untouched():
    """The image mode is one per redaction: NONE would leave the logo in place
    and report it removed."""
    def draw(doc, page):
        photo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), True)
        photo.set_rect(photo.irect, (30, 120, 30, 128))
        page.insert_image(pymupdf.Rect(100, 100, 300, 300), pixmap=photo)
        page.insert_image(pymupdf.Rect(310, 150, 350, 170), pixmap=logo_pixmap())
    session = PyMuPdfEditor().open(build(draw))
    with pytest.raises(ToolRejected, match="transparent"):
        session.redact_area(1, (250, 140, 360, 180))
    with pymupdf.open(stream=session.save(drop=[], mark=None)) as doc:
        assert len(doc[0].get_images()) == 2
