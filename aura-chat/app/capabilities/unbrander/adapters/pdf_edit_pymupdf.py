"""PdfEditor over PyMuPDF: the mechanics of the unbrand tools, no judgement.

Redaction settings come from the unbrand-builder-docs skill, where each one was
learned on real builder PDFs. `import pymupdf`, never the legacy `fitz` alias.
"""

import io

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from ..domain import BBox, DrawnElement, MarkPosition, ToolRejected, Word, missing
from .pdf_pymupdf import page_words

# A word box is shrunk before it is redacted: MuPDF removes every glyph whose box
# touches the rect. Sideways by a hair, so the next word keeps its first letter.
# Vertically to the middle band, because glyph boxes span the full line height
# and with tight leading they overlap the line below: in the spike brochure,
# redacting ARISTA also took the "CERTI" of "CERTIFIED" under it.
SHRINK = 0.5
BAND = 0.35  # share of the word's height left out at the top and at the bottom

# Renders go to a model to spot logos; exact words come from the text layer and
# verify() renders for OCR itself, so JPEG's softening costs little. 85, not
# lower, so a small faint monogram stays visible.
JPEG_QUALITY = 85

# Shape groups closer than this many points are one element. pymupdf's own
# cluster_drawings splits the ARISTA logo in two and BILD's in three.
ELEMENT_GAP = 6
BACKGROUND_SHARE = 0.5  # a drawing over this share of the page is its background
NEUTRAL_SPREAD = 0.15   # RGB channels closer than this are a shade of gray
MARK_COLOUR = (220, 0, 0)
LABEL_SIZE = 26  # pixels; Pillow's default 10 is unreadable on a 2300-pixel-wide render

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

    def _page(self, page: int) -> "pymupdf.Page":
        return self._doc[page - 1]

    def page_size(self, page: int) -> tuple[float, float]:
        rect = self._page(page).rect
        return rect.width, rect.height

    def words(self, page: int) -> list[Word]:
        return page_words(self._page(page))

    def elements(self, page: int) -> list[DrawnElement]:
        pdf_page = self._page(page)
        out = [group for group, _ in _shape_groups(pdf_page)]
        # get_images lists an xref once per XObject that uses it; each placement once.
        for xref in dict.fromkeys(image[0] for image in pdf_page.get_images(full=True)):
            out += [DrawnElement(kind="image", bbox=tuple(rect))
                    for rect in pdf_page.get_image_rects(xref)]
        return out

    def groups_covered(self, page: int, box: BBox) -> list[DrawnElement]:
        return [group for group, members in _shape_groups(self._page(page))
                if any(_inside(member, box) for member in members)]

    def shapes_cut(self, page: int, box: BBox) -> int:
        pdf_page = self._page(page)
        limit = BACKGROUND_SHARE * pdf_page.rect.get_area()
        rect = pymupdf.Rect(box)
        covered = rect + (-1, -1, 1, 1)
        return sum(1 for drawing in pdf_page.get_drawings()
                   if drawing["rect"].get_area() <= limit and drawing["rect"].intersects(rect)
                   and drawing["rect"] not in covered)

    def render(self, page: int, dpi: int,
               marks: list[tuple[int, BBox]] | None = None) -> bytes:
        pixmap = self._page(page).get_pixmap(dpi=dpi, alpha=False)
        if not marks:
            return pixmap.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
        picture = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        draw = ImageDraw.Draw(picture)
        font = ImageFont.load_default(size=LABEL_SIZE)
        scale = dpi / 72
        for number, (x0, y0, x1, y1) in marks:
            draw.rectangle((x0 * scale, y0 * scale, x1 * scale, y1 * scale),
                           outline=MARK_COLOUR, width=2)
            # The number on a white tag at the box's top-left corner, inside the
            # picture, so it stays readable over a photo or a dark band.
            left = min(max(x0 * scale, 0), pixmap.width - LABEL_SIZE * 2)
            top = min(max(y0 * scale - LABEL_SIZE - 4, 0), pixmap.height - LABEL_SIZE - 4)
            tag = draw.textbbox((left + 3, top + 1), str(number), font=font)
            draw.rectangle((tag[0] - 3, tag[1] - 2, tag[2] + 3, tag[3] + 2), fill=(255, 255, 255),
                           outline=MARK_COLOUR)
            draw.text((left + 3, top + 1), str(number), fill=MARK_COLOUR, font=font)
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=JPEG_QUALITY)
        return out.getvalue()

    def redact_text(self, page: int, boxes: list[BBox]) -> None:
        pdf_page = self._page(page)
        for box in boxes:
            x0, y0, x1, y1 = box
            inset = (y1 - y0) * BAND
            rect = pymupdf.Rect(x0 + SHRINK, y0 + inset, x1 - SHRINK, y1 - inset)
            pdf_page.add_redact_annot(rect, fill=None, cross_out=False)
        # Line art untouched: a floor plan's walls and dimension lines run under its labels.
        pdf_page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                           graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                           text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    def redact_area(self, page: int, box: BBox) -> list[Word]:
        before = self.words(page)
        pdf_page = self._page(page)
        rect = pymupdf.Rect(box)
        image_mode = _image_mode(pdf_page, rect)
        pdf_page.add_redact_annot(rect, fill=None, cross_out=False)
        # A separate pass from redact_text: brand furniture is line art, and one
        # call cannot both keep line art and clear it. Only shapes wholly in the
        # box go; with REMOVE_IF_TOUCHED a logo's box took the panel behind it.
        pdf_page.apply_redactions(images=image_mode,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        # By text, not by box: rewriting a page's content moves unchanged words
        # by about 1e-4 points, and comparing boxes reported ten floor plans'
        # labels as removed when none were (run 7).
        return missing(before, self.words(page))

    def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
        doc = self._doc
        if mark is not None:
            for page in doc:
                if page.number + 1 not in drop:
                    _wordmark(page, mark)
        if drop:
            doc.delete_pages(sorted(page_number - 1 for page_number in drop))
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

    def close(self) -> None:
        if not self._doc.is_closed:
            self._doc.close()


def _image_mode(page: "pymupdf.Page", box: "pymupdf.Rect") -> int:
    """Images wholly in the box are removed. One the box only overlaps is blanked
    where it is covered, unless it has a soft mask (transparency): pymupdf's
    blanking of those came out black (run 6, an image emptied by delete_image) or
    one solid colour (the Bright Side site plan's map). Such an image is left
    alone and the judge sees what remains. The mode is one for the whole call, so
    an image wholly in the box beside such a masked one cannot go: that is
    refused rather than reported done with the image still there."""
    overlapping = []
    for xref, smask, *_ in page.get_images(full=True):
        overlapping += [(rect, smask) for rect in page.get_image_rects(xref)
                        if rect.intersects(box)]
    if all(rect in box for rect, _ in overlapping):
        return pymupdf.PDF_REDACT_IMAGE_REMOVE
    if any(smask and rect not in box for rect, smask in overlapping):
        if any(rect in box for rect, _ in overlapping):
            raise ToolRejected("the area holds a whole image and part of a transparent "
                               "image; the first cannot be removed without damaging the "
                               "second. Leave it")
        return pymupdf.PDF_REDACT_IMAGE_NONE
    return pymupdf.PDF_REDACT_IMAGE_PIXELS


def _shape_groups(page: "pymupdf.Page") -> list[tuple[DrawnElement, list["pymupdf.Rect"]]]:
    """Every group of nearby shapes, with the boxes of the drawings in it."""
    # A page-sized background would join every shape into one group.
    limit = BACKGROUND_SHARE * page.rect.get_area()
    drawings = [drawing for drawing in page.get_drawings()
                if drawing["rect"].get_area() <= limit]
    # Black and gray shapes are grouped apart from coloured ones: a floor plan is
    # drawn in black, and a pale flower watermark a few points from it otherwise
    # joined its group and could not be removed alone.
    out = []
    for neutral in (True, False):
        same = [drawing for drawing in drawings if _is_neutral(drawing) == neutral]
        kind = "shapes" if neutral else "coloured shapes"
        for group in _merged(page.cluster_drawings(drawings=same) if same else [],
                             ELEMENT_GAP):
            bbox = tuple(group)
            out.append((DrawnElement(kind=kind, bbox=bbox),
                        [drawing["rect"] for drawing in same if _inside(drawing["rect"], bbox)]))
    return out


def _inside(inner: "pymupdf.Rect", outer: BBox) -> bool:
    """By coordinates, with a hair of slack: pymupdf says a line's empty
    rectangle is inside nothing."""
    return (inner.x0 >= outer[0] - 0.5 and inner.y0 >= outer[1] - 0.5
            and inner.x1 <= outer[2] + 0.5 and inner.y1 <= outer[3] + 0.5)


def _is_neutral(drawing: dict) -> bool:
    """Black, gray or white: no colour channel stands out."""
    colour = drawing.get("fill") or drawing.get("color")
    if not colour or len(colour) == 1:
        return True
    if len(colour) == 4:  # CMYK
        colour = tuple(1 - min(1.0, channel + colour[3]) for channel in colour[:3])
    return max(colour) - min(colour) < NEUTRAL_SPREAD


def _merged(rects: list["pymupdf.Rect"], gap: float) -> list["pymupdf.Rect"]:
    """Rects within `gap` of each other joined into one, until none are."""
    groups = [pymupdf.Rect(rect) for rect in rects if not rect.is_empty]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            grown = groups[i] + (-gap, -gap, gap, gap)
            for j in range(i + 1, len(groups)):
                if grown.intersects(groups[j]):
                    groups[i] |= groups.pop(j)
                    merged = True
                    break
            if merged:
                break
    return groups


def _wordmark(page: "pymupdf.Page", position: MarkPosition) -> None:
    """Placed as the page is seen. page.rect is the rotated (visible) page, but
    insert_text works in unrotated space, so each point is derotated and the
    letters are turned with the page to read upright."""
    letters = [(ch, color) for word, color in MARK for ch in word]
    width = sum(pymupdf.get_text_length(ch, MARK_FONT, MARK_SIZE) + MARK_TRACKING
                for ch, _ in letters) + MARK_SIZE * 0.5 * (len(MARK) - 1)
    left = (page.rect.width - MARGIN - width if position is MarkPosition.BOTTOM_RIGHT
            else (page.rect.width - width) / 2)
    baseline = page.rect.height - MARGIN
    for word, color in MARK:
        for ch in word:
            page.insert_text(pymupdf.Point(left, baseline) * page.derotation_matrix, ch,
                             fontname=MARK_FONT, fontsize=MARK_SIZE, color=color,
                             fill_opacity=MARK_OPACITY, rotate=page.rotation)
            left += pymupdf.get_text_length(ch, MARK_FONT, MARK_SIZE) + MARK_TRACKING
        left += MARK_SIZE * 0.5


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
    for number, xref in enumerate(sorted((doc.get_ocgs() or {}).keys()), start=1):
        doc.xref_set_key(xref, "Name", f"(Layer {number})")
