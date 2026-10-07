"""The code gate between M2 (clean) and the human.

Pure: compares the facts of the source PDF with the facts of the cleaned one and
trusts nothing the model said about its own work. In the spike, Haiku's report
claimed removals its PDF did not contain.
"""

import bisect
import re
import unicodedata

from .domain import (
    OCR_MODES,
    BBox,
    Check,
    Finding,
    HitList,
    PageFacts,
    PdfFacts,
    Severity,
    VerifyReport,
)

GENERIC = {
    "url": re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE),
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "phone": re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}\b"),
    "domain": re.compile(r"\b[\w-]+\.(?:com|ca|net|org|homes)\b", re.IGNORECASE),
}

# Words the cleaned PDF may hold that the source never did: the Aura Key mark,
# and the substitutes the skill uses when a builder name is cut from a sentence.
ALLOWED_NEW_WORDS = {"aura", "key", "realty", "vendor", "builder", "the"}

# OCR misreads, folded the same way on both sides before matching. "rn" for "m"
# is two edits, more than the fuzzy match allows, so it is folded instead.
OCR_FOLD = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "5": "s"})

SHORT = 3        # below this a term matches only as a whole, case-sensitive word
OCR_SQUASH = 5   # from this length OCR text is matched with spacing removed
OCR_FUZZY = 6    # from this length one OCR edit is tolerated
COVERED = 0.9    # share of a text or image box hidden by a later opaque fill


def verify(
    source: PdfFacts,
    output: PdfFacts,
    hits: HitList,
    dropped_pages: list[int] | None = None,
) -> VerifyReport:
    terms = hits.terms()
    findings: list[Finding] = []
    for page in output.pages:
        findings += _text_sweep(page, terms)
        findings += _ocr_sweep(page, terms)
        findings += _cover_up(page)
    findings += _raw_bytes(output, terms)
    findings += _numbers(source, output)
    findings += _provenance(source, output)
    findings += _metadata(output)
    findings += _pages(source, output, dropped_pages)
    return VerifyReport(findings=findings)


def _term_pattern(term: str, *, anchored: bool = True) -> re.Pattern:
    """Tolerates one separator between any two characters, so "SouthCal" also
    finds "South Cal", "South-Cal" and letter-spaced "S O U T H C A L"."""
    if len(term) < SHORT:
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])")
    chars = [re.escape(c) for c in term if c.isalnum()]
    body = r"[\s\-_.·]?".join(chars)
    if anchored:
        body = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
    return re.compile(body, re.IGNORECASE)


def _page_text(page: PageFacts) -> tuple[str, list[int]]:
    starts, parts, pos = [], [], 0
    for w in page.words:
        starts.append(pos)
        parts.append(w.text)
        pos += len(w.text) + 1
    return " ".join(parts), starts


def _bbox_at(page: PageFacts, starts: list[int], offset: int) -> BBox | None:
    if not page.words:
        return None
    return page.words[max(bisect.bisect_right(starts, offset) - 1, 0)].bbox


def _text_sweep(page: PageFacts, terms: list[str]) -> list[Finding]:
    text, starts = _page_text(page)
    out = []
    for term in terms:
        for m in _term_pattern(term).finditer(text):
            out.append(Finding(
                check=Check.TEXT_SWEEP, severity=Severity.RETRY, page=page.number,
                detail=f"{term!r} in the text layer: {m.group()!r}",
                bbox=_bbox_at(page, starts, m.start()),
            ))
    # A flag, not a retry: brochures quote legitimate addresses too (a
    # natural-resources.canada.ca Energy Star link, in the spike). A builder's own
    # URL carries the builder's name, and the hit list catches that above.
    for kind, pattern in GENERIC.items():
        for m in pattern.finditer(text):
            out.append(Finding(
                check=Check.TEXT_SWEEP, severity=Severity.FLAG, page=page.number,
                detail=f"{kind} in the text layer: {m.group()!r}",
                bbox=_bbox_at(page, starts, m.start()),
            ))
    return out


def _raw_bytes(output: PdfFacts, terms: list[str]) -> list[Finding]:
    """Unanchored: object names run words together ("ARISTA_LOGO", "SouthCalDT").
    Terms under four characters would match inside unrelated names, so they are
    left to the text and OCR sweeps."""
    out = []
    for term in terms:
        if len(term) < 4:
            continue
        m = _term_pattern(term, anchored=False).search(output.object_text)
        if m:
            a, b = max(m.start() - 30, 0), m.end() + 30
            out.append(Finding(
                check=Check.RAW_BYTES, severity=Severity.RETRY,
                detail=f"{term!r} inside the PDF's objects: {output.object_text[a:b]!r}",
            ))
    return out


def _fold(text: str) -> str:
    return text.lower().translate(OCR_FOLD).replace("rn", "m")


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(text))


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _fuzzy_in(haystack: str, needle: str) -> bool:
    """One edit apart, found without scanning every window: a match with at most
    one edit keeps one of the needle's two halves intact."""
    if needle in haystack:
        return True
    n, half = len(needle), len(needle) // 2
    for piece, offset in ((needle[:half], 0), (needle[half:], half)):
        at = haystack.find(piece)
        while at != -1:
            start = at - offset
            for size in (n - 1, n, n + 1):
                for s in (start - 1, start, start + 1):
                    if 0 <= s and s + size <= len(haystack) and _within_one_edit(
                        haystack[s:s + size], needle
                    ):
                        return True
            at = haystack.find(piece, at + 1)
    return False


def _ocr_sweep(page: PageFacts, terms: list[str]) -> list[Finding]:
    if not page.ocr:
        return [Finding(
            check=Check.OCR_SWEEP, severity=Severity.BLOCK, page=page.number,
            detail="OCR was not run on this page; pixels were never checked",
        )]
    out = []
    for mode in OCR_MODES:
        raw = page.ocr.get(mode, "")
        squashed, words = _squash(raw), set(re.findall(r"[a-z0-9]+", _fold(raw)))
        for term in terms:
            if len(term) < SHORT:
                continue  # two letters turn up in any OCR noise
            key = _squash(term)
            if len(key) >= OCR_SQUASH:
                found = _fuzzy_in(squashed, key) if len(key) >= OCR_FUZZY else key in squashed
            else:
                found = key in words
            if found:
                out.append(Finding(
                    check=Check.OCR_SWEEP, severity=Severity.RETRY, page=page.number,
                    detail=f"{term!r} visible in the rendered page (OCR, {mode})",
                ))
    return out


def _area(b: BBox) -> float:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def _overlap(a: BBox, b: BBox) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _cover_up(page: PageFacts) -> list[Finding]:
    out, below = [], []
    for item in page.paint:
        if item.kind in ("text", "image"):
            below.append(item)
            continue
        if not (item.kind == "path" and item.opaque):
            continue
        visible = []
        for under in below:
            size = _area(under.bbox)
            if size and _overlap(item.bbox, under.bbox) / size >= COVERED:
                out.append(Finding(
                    check=Check.COVER_UP, severity=Severity.RETRY, page=page.number,
                    detail=f"opaque shape drawn over {under.kind}: hidden, not removed",
                    bbox=under.bbox,
                ))
            else:
                visible.append(under)
        below = visible
    return out


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _number_key(token: str) -> str:
    key = token.replace(",", "").lstrip("0") or "0"
    return key.removesuffix(".0")


def _numbers_in(facts: PdfFacts) -> set[str]:
    return {_number_key(t) for p in facts.pages for w in p.words for t in NUMBER.findall(w.text)}


def _numbers(source: PdfFacts, output: PdfFacts) -> list[Finding]:
    known, out = _numbers_in(source), []
    for page in output.pages:
        for w in page.words:
            for token in NUMBER.findall(w.text):
                if _number_key(token) not in known:
                    out.append(Finding(
                        check=Check.NUMBERS, severity=Severity.BLOCK, page=page.number,
                        detail=f"{token!r} is not in the source", bbox=w.bbox,
                    ))
    return out


def _word_key(text: str) -> str:
    """NFKC first: a re-typeset "reﬂects" uses the fl ligature, the source does not."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"^[^\w]+|[^\w]+$", "", text)


def _provenance(source: PdfFacts, output: PdfFacts) -> list[Finding]:
    known = {_word_key(w.text) for p in source.pages for w in p.words}
    out = []
    for page in output.pages:
        new = [w for w in page.words if _is_new(_word_key(w.text), known)]
        if new:
            listed = ", ".join(repr(w.text) for w in new[:20])
            more = f" and {len(new) - 20} more" if len(new) > 20 else ""
            out.append(Finding(
                check=Check.PROVENANCE, severity=Severity.FLAG, page=page.number,
                detail=f"words not in the source: {listed}{more}", bbox=new[0].bbox,
            ))
    return out


def _is_new(key: str, known: set[str]) -> bool:
    if not key or key in known or key in ALLOWED_NEW_WORDS:
        return False
    # The mark is set letter by letter; numbers have their own check.
    return not (len(key) == 1 or NUMBER.fullmatch(key))


def _metadata(output: PdfFacts) -> list[Finding]:
    problems = [f"{k}={v!r}" for k, v in output.metadata.items() if v]
    if output.xmp.strip():
        problems.append("XMP metadata present")
    for name, count in (("annotations", output.annotations), ("links", output.links),
                        ("embedded files", output.embedded_files)):
        if count:
            problems.append(f"{count} {name}")
    if not problems:
        return []
    return [Finding(check=Check.METADATA, severity=Severity.RETRY, detail="; ".join(problems))]


def _pages(source: PdfFacts, output: PdfFacts, dropped: list[int] | None) -> list[Finding]:
    def flag(detail: str, page: int | None = None) -> Finding:
        return Finding(check=Check.PAGES, severity=Severity.FLAG, detail=detail, page=page)

    gone = set(dropped or [])
    kept = [p for p in source.pages if p.number not in gone]
    if len(kept) != len(output.pages):
        declared = f"{len(gone)} declared dropped" if dropped is not None else "none declared"
        return [flag(f"source has {len(source.pages)} pages, output {len(output.pages)}; "
                     f"{declared}")]
    out = []
    for src, dst in zip(kept, output.pages):
        if abs(src.width - dst.width) > 1 or abs(src.height - dst.height) > 1:
            out.append(flag(f"size changed from {src.width:.0f}x{src.height:.0f} "
                            f"(source page {src.number}) to {dst.width:.0f}x{dst.height:.0f}",
                            dst.number))
    return out
