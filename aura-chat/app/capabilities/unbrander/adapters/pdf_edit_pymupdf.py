"""PdfEditor over PyMuPDF: the mechanics of the M2 tools, no judgement.

Redaction settings come from the unbrand-builder-docs skill, where each one was
learned on real builder PDFs. `import pymupdf`, never the legacy `fitz` alias.
"""

import pymupdf

from ..domain import BBox, ImageRef, MarkPosition, Word

# A word box is shrunk before it is redacted: MuPDF removes every glyph whose box
# touches the rect. Sideways by a hair, so the next word keeps its first letter.
# Vertically to the middle band, because glyph boxes span the full line height
# and with tight leading they overlap the line below: in the spike brochure,
# redacting ARISTA also took the "CERTI" of "CERTIFIED" under it.
SHRINK = 0.5
BAND = 0.35  # share of the word's height left out at the top and at the bottom

MARGIN = 36  # points from the page edge
MARK_SIZE = 7.5
MARK_TRACKING = 1.6
MARK_OPACITY = 0.55
NAVY = (0.055, 0.102, 0.141)  # #0E1A24
GOLD = (0.788, 0.635, 0.153)  # #C9A227
MARK = (("AURA", NAVY), ("KEY", GOLD), ("REALTY", NAVY))
MARK_FONT = "times-roman"


class PyMuPdfEditor:
    def open(self, pdf: bytes) -> "PyMuPdfSession":
        return PyMuPdfSession(pymupdf.open(stream=pdf, filetype="pdf"))


class PyMuPdfSession:
    def __init__(self, doc: "pymupdf.Document") -> None:
        self._doc = doc
        self.page_count = doc.page_count
        self._drawn_on: dict[int, list[int]] | None = None

    def _page(self, page: int) -> "pymupdf.Page":
        return self._doc[page - 1]

    def page_size(self, page: int) -> tuple[float, float]:
        r = self._page(page).rect
        return r.width, r.height

    def words(self, page: int) -> list[Word]:
        return [Word(text=w[4], bbox=tuple(w[:4])) for w in self._page(page).get_text("words")]

    def images(self, page: int) -> list[ImageRef]:
        if self._drawn_on is None:
            # Built once, rebuilt only after delete_image, which puts a new
            # blank image on the page.
            self._drawn_on = {}
            for q in self._doc:
                for xref in {i[0] for i in q.get_images(full=True)}:
                    self._drawn_on.setdefault(xref, []).append(q.number + 1)
        drawn_on = self._drawn_on
        p = self._page(page)
        out = []
        # get_images lists an xref once per XObject that uses it; each placement once.
        for xref in dict.fromkeys(i[0] for i in p.get_images(full=True)):
            for rect in p.get_image_rects(xref):
                out.append(ImageRef(id=xref, bbox=tuple(rect), pages=drawn_on[xref]))
        return out

    def render(self, page: int, dpi: int) -> bytes:
        return self._page(page).get_pixmap(dpi=dpi, alpha=False).tobytes("png")

    def redact_text(self, page: int, boxes: list[BBox]) -> None:
        p = self._page(page)
        for box in boxes:
            x0, y0, x1, y1 = box
            inset = (y1 - y0) * BAND
            r = pymupdf.Rect(x0 + SHRINK, y0 + inset, x1 - SHRINK, y1 - inset)
            p.add_redact_annot(r, fill=None, cross_out=False)
        # Line art untouched: a floor plan's walls and dimension lines run under its labels.
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                           graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                           text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    def redact_area(self, page: int, box: BBox) -> list[Word]:
        before = self.words(page)
        p = self._page(page)
        p.add_redact_annot(pymupdf.Rect(box), fill=None, cross_out=False)
        # A separate pass from redact_text: brand furniture is line art, and one
        # call cannot both keep line art and clear it.
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                           graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                           text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        after = {(w.text, w.bbox) for w in self.words(page)}
        return [w for w in before if (w.text, w.bbox) not in after]

    def delete_image(self, page: int, image_id: int) -> None:
        self._page(page).delete_image(image_id)
        self._drawn_on = None

    def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
        doc = self._doc
        if mark is not None:
            for page in doc:
                if page.number + 1 not in drop:
                    _wordmark(page, mark)
        if drop:
            doc.delete_pages(sorted(p - 1 for p in drop))
        for page in doc:
            for annot in list(page.annots()):
                page.delete_annot(annot)
        # Info dict, catalog XMP, links, attachments, JavaScript. Hidden text stays:
        # in a scanned brochure it is the OCR layer that makes prices searchable,
        # and redact_terms has already taken the builder's names out of it.
        doc.scrub(hidden_text=False)
        _strip_object_metadata(doc)
        _rename_layers(doc)
        try:
            # garbage=4 drops the objects nothing points to any more, so what
            # was removed is gone from the file, not only from the page.
            return doc.tobytes(garbage=4, deflate=True)
        finally:
            doc.close()


def _wordmark(page: "pymupdf.Page", position: MarkPosition) -> None:
    """Placed as the page is seen. page.rect is the rotated (visible) page, but
    insert_text works in unrotated space, so each point is derotated and the
    letters are turned with the page to read upright."""
    letters = [(ch, color) for word, color in MARK for ch in word]
    width = sum(pymupdf.get_text_length(ch, MARK_FONT, MARK_SIZE) + MARK_TRACKING
                for ch, _ in letters) + MARK_SIZE * 0.5 * (len(MARK) - 1)
    x = (page.rect.width - MARGIN - width if position is MarkPosition.BOTTOM_RIGHT
         else (page.rect.width - width) / 2)
    y = page.rect.height - MARGIN
    for word, color in MARK:
        for ch in word:
            page.insert_text(pymupdf.Point(x, y) * page.derotation_matrix, ch,
                             fontname=MARK_FONT, fontsize=MARK_SIZE, color=color,
                             fill_opacity=MARK_OPACITY, rotate=page.rotation)
            x += pymupdf.get_text_length(ch, MARK_FONT, MARK_SIZE) + MARK_TRACKING
        x += MARK_SIZE * 0.5


def _strip_object_metadata(doc: "pymupdf.Document") -> None:
    """scrub() empties the catalog's XMP only. Any object can carry its own; in
    the spike, eleven images in Opus's output kept the designer's file names."""
    for xref in range(1, doc.xref_length()):
        try:
            if doc.xref_get_key(xref, "Metadata")[0] != "null":
                doc.xref_set_key(xref, "Metadata", "null")
        except RuntimeError:  # a free or broken entry in a damaged xref table
            continue


def _rename_layers(doc: "pymupdf.Document") -> None:
    """Layer names are never drawn but stay in the file: "SouthCal_DT 2001"."""
    for n, xref in enumerate(sorted((doc.get_ocgs() or {}).keys()), start=1):
        doc.xref_set_key(xref, "Name", f"(Layer {n})")
