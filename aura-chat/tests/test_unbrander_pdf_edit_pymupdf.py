"""The pymupdf edit adapter, on tiny PDFs built inside each test. No binaries in git."""

import shutil

import pymupdf
import pytest

from app.capabilities.unbrander.adapters.pdf_edit_pymupdf import PyMuPdfEditor
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.domain import HitList, MarkPosition
from app.capabilities.unbrander.tools import Toolbox
from app.capabilities.unbrander.verify import verify

has_tesseract = shutil.which("tesseract") is not None


def build(draw, pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        draw(doc, doc.new_page(width=612, height=792))
    return doc.tobytes()


def logo_pixmap() -> "pymupdf.Pixmap":
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
    pix.set_rect(pix.irect, (200, 30, 30))
    return pix


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
        pix = doc[0].get_pixmap(clip=pymupdf.Rect(450, 40, 500, 80))
        assert set(pix.samples) == {255}  # white: the red logo is gone
        assert "Lot 12" in doc[0].get_text()


def test_images_and_delete_image():
    def draw(doc, page):
        page.insert_image(pymupdf.Rect(20, 20, 100, 60), pixmap=logo_pixmap())
    pdf = build(draw)
    session = PyMuPdfEditor().open(pdf)
    [ref] = session.images(1)
    assert ref.bbox == pytest.approx((20, 20, 100, 60))
    session.delete_image(1, ref.id)
    with pymupdf.open(stream=session.save(drop=[], mark=None)) as doc:
        pix = doc[0].get_pixmap(clip=pymupdf.Rect(30, 30, 90, 50))
        assert set(pix.samples) == {255}


def test_save_drops_pages_and_marks_every_kept_page_in_the_same_place():
    pdf = build(lambda d, p: p.insert_text((72, 72), f"Page {p.number + 1}"), pages=3)
    out = PyMuPdfEditor().open(pdf).save(drop=[2], mark=MarkPosition.BOTTOM_RIGHT)
    with pymupdf.open(stream=out) as doc:
        assert [p.get_text().split()[:2] for p in doc] == [["Page", "1"], ["Page", "3"]]
        spots = [p.search_for("A")[-1] for p in doc]
        assert spots[0] == spots[1]
        assert spots[0].x0 > 450 and spots[0].y1 > 740


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
        page.insert_text((72, 200), "The Aspen  1,850 sq ft  $1,234,990", fontsize=14)
    pdf = build(draw, pages=2)
    hits = HitList(builder="Arista Homes", project="SouthCal")
    inspector = PyMuPdfInspector()
    source = inspector.inspect(pdf, ocr=False)
    tb = Toolbox(PyMuPdfEditor().open(pdf), source, hits)
    tb.redact_terms(["SouthCal", "Arista Homes"])
    tb.drop_page(2, "duplicate")
    tb.add_mark("bottom_right")
    done = tb.finish()
    report = verify(source, inspector.inspect(done.pdf, ocr=has_tesseract), hits,
                    dropped_pages=done.dropped_pages)
    assert [f for f in report.findings if f.severity != "flag"] == []
    assert report.passed
