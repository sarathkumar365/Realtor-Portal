"""The pymupdf adapter, on tiny PDFs built inside each test. No binaries in git.

OCR tests need the tesseract binary. They skip without it and say why; the
agent's startup script is what installs it.
"""

import shutil

import pymupdf
import pytest

from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.ports import OcrUnavailable

needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract not installed: OCR untested"
)


def build(draw) -> bytes:
    doc = pymupdf.open()
    draw(doc, doc.new_page(width=612, height=792))
    return doc.tobytes()


def inspect(pdf: bytes, ocr: bool = False):
    return PyMuPdfInspector().inspect(pdf, ocr=ocr)


def test_words_come_with_their_boxes():
    facts = inspect(build(lambda d, p: p.insert_text((72, 72), "Lot 12 $1,234,567")))
    assert [w.text for w in facts.pages[0].words] == ["Lot", "12", "$1,234,567"]
    assert facts.pages[0].words[0].bbox[0] == pytest.approx(72, abs=1)
    assert (facts.pages[0].number, facts.pages[0].width) == (1, 612)


def test_metadata_reports_only_what_is_set():
    def draw(doc, page):
        doc.set_metadata({"author": "Arista Homes"})
    assert inspect(build(draw)).metadata == {"author": "Arista Homes"}


def test_layer_names_reach_object_text():
    def draw(doc, page):
        doc.add_ocg("SouthCal_DT 2001")
    assert "SouthCal_DT 2001" in inspect(build(draw)).object_text


def test_xmp_attached_to_any_object_reaches_object_text():
    """Opus's spike output kept the designer's file names in per-image XMP."""
    def draw(doc, page):
        xref = doc.get_new_xref()
        doc.update_object(xref, "<</Type/Metadata/Subtype/XML>>")
        doc.update_stream(xref, b"<rdf:li>SouthCal_DT 2001</rdf:li>")
        doc.xref_set_key(page.xref, "Metadata", f"{xref} 0 R")
    assert "SouthCal_DT 2001" in inspect(build(draw)).object_text


@pytest.mark.parametrize("encoded", ["<536F75746843616C>", "<FEFF0053006F00750074006800430061006C>"])
def test_hex_strings_are_decoded_in_object_text(encoded):
    def draw(doc, page):
        xref = doc.get_new_xref()
        doc.update_object(xref, f"<</Type/Note/Title {encoded}>>")
        doc.xref_set_key(page.xref, "Note", f"{xref} 0 R")
    text = inspect(build(draw)).object_text
    assert "SouthCal" in text and "<</" in text


def test_a_box_drawn_over_text_shows_in_paint_order():
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(0, 0, 612, 40), color=None, fill=(0, 0.5, 0.5),
                       fill_opacity=0.4)
        page.insert_text((72, 72), "SouthCal")
        page.draw_rect(pymupdf.Rect(60, 55, 300, 80), color=None, fill=(1, 1, 1))
    paint = inspect(build(draw)).pages[0].paint
    assert [(p.kind, p.opaque) for p in paint] == [("path", False), ("text", False),
                                                   ("path", True)]


def test_no_ocr_unless_asked():
    assert inspect(build(lambda d, p: None)).pages[0].ocr == {}


def test_missing_tesseract_raises_rather_than_returning_nothing(monkeypatch):
    def missing(tessdata=None):
        raise RuntimeError("No tessdata specified and Tesseract is not installed")
    monkeypatch.setattr(pymupdf, "get_tessdata", missing)
    with pytest.raises(OcrUnavailable):
        inspect(build(lambda d, p: None), ocr=True)


@needs_tesseract
def test_ocr_reads_white_ink_on_a_teal_panel():
    """The leak that shipped: invisible to the text layer, visible to a buyer."""
    def draw(doc, page):
        page.draw_rect(pymupdf.Rect(40, 300, 572, 420), color=None, fill=(0, 0.5, 0.5))
        page.insert_text((60, 380), "SOUTHCAL", fontsize=48, color=(1, 1, 1), render_mode=0)
    pdf = build(draw)
    doc = pymupdf.open(stream=pdf)
    # Strip the text layer so only pixels carry the name, as in a flattened brochure.
    pix = doc[0].get_pixmap(dpi=150)
    flat = pymupdf.open()
    flat.new_page(width=612, height=792).insert_image(pymupdf.Rect(0, 0, 612, 792), pixmap=pix)
    facts = inspect(flat.tobytes(), ocr=True)
    page = facts.pages[0]
    assert page.words == []
    assert set(page.ocr) == {"normal", "inverted", "light"}
    assert "SOUTHCAL" in page.ocr["light"].upper().replace(" ", "")
