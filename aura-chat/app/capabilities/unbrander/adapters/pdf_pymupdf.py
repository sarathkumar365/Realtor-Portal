"""PdfInspector over PyMuPDF. The only file that imports pymupdf or Pillow.

`import pymupdf`, never the legacy `fitz` alias.
"""

import re

import pymupdf
from PIL import Image, ImageOps

from ..domain import OCR_MODES, PageFacts, Paint, PdfFacts, Word
from ..ports import OcrUnavailable

OCR_DPI = 150
# Above this luminance a pixel counts as light ink. Teal, navy and photo
# backgrounds fall below it; white lettering on them does not.
LIGHT_INK = 200

PAINT_KINDS = {
    "fill-text": "text", "stroke-text": "text",
    "fill-image": "image", "fill-path": "path", "fill-shade": "path",
}
METADATA_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")
# A hex string, not the second "<" of a dictionary's "<<". A trailing ">>" is
# fine: a hex string often ends the dictionary it sits in.
HEX_STRING = re.compile(r"(?<!<)<([0-9A-Fa-f\s]+)>")


class PyMuPdfInspector:
    def __init__(self, tessdata: str | None = None) -> None:
        self._tessdata = tessdata

    def inspect(self, pdf: bytes, *, ocr: bool) -> PdfFacts:
        tessdata = self._find_tessdata() if ocr else None
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            return PdfFacts(
                pages=[self._page(page, tessdata) for page in doc],
                metadata={k: v for k in METADATA_KEYS if (v := (doc.metadata or {}).get(k))},
                xmp=doc.get_xml_metadata() or "",
                annotations=sum(1 for page in doc for _ in page.annots()),
                links=sum(len(page.get_links()) for page in doc),
                embedded_files=doc.embfile_count(),
                object_text=_object_text(doc),
            )

    def _find_tessdata(self) -> str:
        try:
            return pymupdf.get_tessdata(self._tessdata)
        except Exception as e:  # pymupdf raises a bare RuntimeError with no stable type
            raise OcrUnavailable(f"tesseract language data not found: {e}") from e

    def _page(self, page: "pymupdf.Page", tessdata: str | None) -> PageFacts:
        return PageFacts(
            number=page.number + 1,
            width=page.rect.width,
            height=page.rect.height,
            words=[Word(text=w[4], bbox=tuple(w[:4])) for w in page.get_text("words")],
            paint=_paint(page),
            ocr=_ocr(page, tessdata) if tessdata else {},
        )


def _paint(page: "pymupdf.Page") -> list[Paint]:
    # get_drawings() seqno is the index into get_bboxlog(): both walk the same display list.
    opaque = {
        d["seqno"] for d in page.get_drawings()
        if d.get("fill") is not None and (d.get("fill_opacity") or 0) >= 0.99
    }
    out = []
    for i, (kind, bbox) in enumerate(page.get_bboxlog()):
        if kind in PAINT_KINDS:
            out.append(Paint(kind=PAINT_KINDS[kind], bbox=tuple(bbox), opaque=i in opaque))
    return out


def _ocr(page: "pymupdf.Page", tessdata: str) -> dict[str, str]:
    pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY, alpha=False)
    gray = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    images = {
        "normal": gray,
        "inverted": ImageOps.invert(gray),
        "light": gray.point(lambda v: 0 if v > LIGHT_INK else 255),
    }
    return {mode: _ocr_text(images[mode], tessdata) for mode in OCR_MODES}


def _ocr_text(image: "Image.Image", tessdata: str) -> str:
    # RGB, not gray: pdfocr on a gray pixmap returns an empty text layer, silently.
    rgb = image.convert("RGB")
    pix = pymupdf.Pixmap(pymupdf.csRGB, rgb.width, rgb.height, rgb.tobytes(), False)
    with pymupdf.open("pdf", pix.pdfocr_tobytes(language="eng", tessdata=tessdata)) as ocr:
        return "\n".join(page.get_text() for page in ocr)


def _object_text(doc: "pymupdf.Document") -> str:
    """Object definitions, plus the bodies of metadata streams: names, labels and
    XMP of things that may never be drawn. Every image can carry its own XMP; in
    the spike, Opus's output kept "SouthCal_DT 2001" and the designer's
    /Volumes/.../ARISTA/ paths in eleven of them. Other stream bodies (content,
    fonts, pixels) are left to the text and OCR sweeps. Hex strings, plain or UTF-16, are
    decoded so a name stored as <FEFF0053...> is searchable like a plain one."""
    parts = [layer["name"] for layer in (doc.get_ocgs() or {}).values()]
    for xref in range(1, doc.xref_length()):
        try:
            parts.append(doc.xref_object(xref, compressed=True))
            if doc.xref_get_key(xref, "Type") == ("name", "/Metadata"):
                parts.append((doc.xref_stream(xref) or b"").decode("utf-8", "replace"))
        except RuntimeError:  # a free or broken entry in a damaged xref table
            continue
    text = "\n".join(parts)
    return HEX_STRING.sub(lambda m: _decode_hex(m.group(1)), text)


def _decode_hex(hex_body: str) -> str:
    digits = re.sub(r"\s", "", hex_body)
    if len(digits) % 2:
        digits += "0"  # the PDF spec pads an odd final digit with 0
    raw = bytes.fromhex(digits)
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    return raw.decode("latin-1")
