"""The code gate between the unbrand step and the human.

Pure: compares the facts of the source PDF with the facts of the cleaned one and
trusts nothing the model said about its own work. In the spike, Haiku's report
claimed removals its PDF did not contain.
"""

import bisect
import re
import unicodedata

from .domain import (
    EMAIL,
    OCR_MODES,
    PHONE,
    SHORT,
    BBox,
    Check,
    Finding,
    HitList,
    PageFacts,
    PdfFacts,
    Removal,
    Severity,
    VerifyReport,
    Word,
    area,
    joined,
    missing,
    overlap,
    term_pattern,
    words_in_span,
)

# Domain endings flagged when a bare domain appears without "www" or a scheme.
# Narrow on purpose: a wider pattern flags every "e.g." and "St.Clair" to the
# approver, and a builder's own domain carries its name, which the hit list catches.
FLAGGED_DOMAIN_ENDINGS = ("com", "ca", "net", "org", "homes")
GENERIC = {
    "url": re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE),
    "email": EMAIL,
    "phone": PHONE,
    "domain": re.compile(rf"\b[\w-]+\.(?:{'|'.join(FLAGGED_DOMAIN_ENDINGS)})\b",
                         re.IGNORECASE),
}

# Words the cleaned PDF may hold that the source never did: the Aura Key mark,
# and the substitutes the skill uses when a builder name is cut from a sentence.
ALLOWED_NEW_WORDS = {"aura", "key", "realty", "vendor", "builder", "the"}

# OCR misreads, folded the same way on both sides before matching. "rn" for "m"
# is two edits, more than the fuzzy match allows, so it is folded instead.
OCR_FOLD = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "5": "s"})

OCR_SQUASH = 5   # from this length OCR text is matched with spacing removed
OCR_FUZZY = 6    # from this length one OCR edit is tolerated
COVERED = 0.9    # share of a text or image box hidden by a later opaque fill
# The damage check's picture comparison. A pixel counts as changed when its gray
# level moved by more than PIXEL_CHANGE; a page is flagged when more than
# CHANGED_SHARE of it changed outside every removal. Anti-aliasing at the edge of
# a removal moves a pixel or two, hence the slack around each area.
PIXEL_CHANGE = 48
CHANGED_SHARE = 0.002
AREA_SLACK = 2.0     # points around each removal area
MARK_STRIP = 50.0    # points at the bottom where the Aura Key mark goes
# Object names run words together, so the raw-bytes sweep matches unanchored;
# terms shorter than this would match inside unrelated names.
RAW_BYTES_MIN_LENGTH = 4
CONTEXT_CHARS = 30   # characters quoted either side of a raw-bytes match
LISTED_WORDS = 20    # words quoted in one finding; the rest are counted
SIZE_TOLERANCE = 1.0  # points a kept page's width or height may move


def verify(
    source: PdfFacts,
    output: PdfFacts,
    hits: HitList,
    dropped_pages: list[int] | None = None,
    removals: list[Removal] | None = None,
    removed_terms: list[str] | None = None,
) -> VerifyReport:
    """`removed_terms` are names removed on purpose beyond the hit list (the
    sort's): their absence is not damage. They are not swept for: a short one
    such as "ARISTA" matched OCR noise ("earlrta") within one edit, and every
    match in the text layer was removed by redact_terms anyway."""
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
    findings += _damage(source, output, [*terms, *(removed_terms or [])], dropped_pages,
                        removals or [])
    return VerifyReport(findings=findings)


def _bbox_at(page: PageFacts, starts: list[int], offset: int) -> BBox | None:
    if not page.words:
        return None
    return page.words[max(bisect.bisect_right(starts, offset) - 1, 0)].bbox


def _text_sweep(page: PageFacts, terms: list[str]) -> list[Finding]:
    text, starts = joined(page.words)
    out = []
    for term in terms:
        for match in term_pattern(term).finditer(text):
            out.append(Finding(
                check=Check.TEXT_SWEEP, severity=Severity.RETRY, page=page.number,
                detail=f"{term!r} in the text layer: {match.group()!r}",
                bbox=_bbox_at(page, starts, match.start()),
            ))
    # A flag, not a retry: brochures quote legitimate addresses too (a
    # natural-resources.canada.ca Energy Star link, in the spike). A builder's own
    # URL carries the builder's name, and the hit list catches that above.
    for kind, pattern in GENERIC.items():
        for match in pattern.finditer(text):
            out.append(Finding(
                check=Check.TEXT_SWEEP, severity=Severity.FLAG, page=page.number,
                detail=f"{kind} in the text layer: {match.group()!r}",
                bbox=_bbox_at(page, starts, match.start()),
            ))
    return out


def _raw_bytes(output: PdfFacts, terms: list[str]) -> list[Finding]:
    """Unanchored: object names run words together ("ARISTA_LOGO", "SouthCalDT").
    Shorter terms are left to the text and OCR sweeps."""
    out = []
    for term in terms:
        if len(term) < RAW_BYTES_MIN_LENGTH:
            continue
        match = term_pattern(term, anchored=False).search(output.object_text)
        if match:
            start = max(match.start() - CONTEXT_CHARS, 0)
            end = match.end() + CONTEXT_CHARS
            out.append(Finding(
                check=Check.RAW_BYTES, severity=Severity.RETRY,
                detail=f"{term!r} inside the PDF's objects: {output.object_text[start:end]!r}",
            ))
    return out


def _fold(text: str) -> str:
    return text.lower().translate(OCR_FOLD).replace("rn", "m")


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(text))


def _within_one_edit(first: str, second: str) -> bool:
    if abs(len(first) - len(second)) > 1:
        return False
    if len(first) == len(second):
        return sum(first_char != second_char
                   for first_char, second_char in zip(first, second)) <= 1
    if len(first) > len(second):
        first, second = second, first
    i = 0
    while i < len(first) and first[i] == second[i]:
        i += 1
    return first[i:] == second[i + 1:]


def _fuzzy_in(haystack: str, needle: str) -> bool:
    """One edit apart, found without scanning every window: a match with at most
    one edit keeps one of the needle's two halves intact."""
    if needle in haystack:
        return True
    needle_length, half = len(needle), len(needle) // 2
    for piece, offset in ((needle[:half], 0), (needle[half:], half)):
        at = haystack.find(piece)
        while at != -1:
            start = at - offset
            for size in (needle_length - 1, needle_length, needle_length + 1):
                for window_start in (start - 1, start, start + 1):
                    if 0 <= window_start and window_start + size <= len(haystack) and (
                        _within_one_edit(haystack[window_start:window_start + size], needle)
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
            size = area(under.bbox)
            if size and overlap(item.bbox, under.bbox) / size >= COVERED:
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
    return {_number_key(token) for page in facts.pages for word in page.words
            for token in NUMBER.findall(word.text)}


def _numbers(source: PdfFacts, output: PdfFacts) -> list[Finding]:
    known, out = _numbers_in(source), []
    for page in output.pages:
        for word in page.words:
            for token in NUMBER.findall(word.text):
                if _number_key(token) not in known:
                    out.append(Finding(
                        check=Check.NUMBERS, severity=Severity.BLOCK, page=page.number,
                        detail=f"{token!r} is not in the source", bbox=word.bbox,
                    ))
    return out


def _word_key(text: str) -> str:
    """NFKC first: a re-typeset "reﬂects" uses the fl ligature, the source does not."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"^[^\w]+|[^\w]+$", "", text)


def _provenance(source: PdfFacts, output: PdfFacts) -> list[Finding]:
    known = {_word_key(word.text) for page in source.pages for word in page.words}
    out = []
    for page in output.pages:
        new = [word for word in page.words if _is_new(_word_key(word.text), known)]
        if new:
            out.append(Finding(
                check=Check.PROVENANCE, severity=Severity.FLAG, page=page.number,
                detail=f"words not in the source: {_listed(new)}", bbox=new[0].bbox,
            ))
    return out


def _is_new(key: str, known: set[str]) -> bool:
    if not key or key in known or key in ALLOWED_NEW_WORDS:
        return False
    # The mark is set letter by letter; numbers have their own check.
    return not (len(key) == 1 or NUMBER.fullmatch(key))


def _metadata(output: PdfFacts) -> list[Finding]:
    problems = [f"{field}={value!r}" for field, value in output.metadata.items() if value]
    if output.xmp.strip():
        problems.append("XMP metadata present")
    for name, count in (("annotations", output.annotations), ("links", output.links),
                        ("embedded files", output.embedded_files)):
        if count:
            problems.append(f"{count} {name}")
    if not problems:
        return []
    return [Finding(check=Check.METADATA, severity=Severity.RETRY, detail="; ".join(problems))]


def _listed(words: list) -> str:
    listed = ", ".join(repr(word.text) for word in words[:LISTED_WORDS])
    more = f" and {len(words) - LISTED_WORDS} more" if len(words) > LISTED_WORDS else ""
    return listed + more


def _paired(source: PdfFacts, output: PdfFacts,
            dropped: list[int] | None) -> list[tuple[PageFacts, PageFacts]] | None:
    """Each kept source page with the output page made from it, or None when the
    counts do not match and pages cannot be paired."""
    gone = set(dropped or [])
    kept = [page for page in source.pages if page.number not in gone]
    if len(kept) != len(output.pages):
        return None
    return list(zip(kept, output.pages))


def _pages(source: PdfFacts, output: PdfFacts, dropped: list[int] | None) -> list[Finding]:
    def flag(detail: str, page: int | None = None) -> Finding:
        return Finding(check=Check.PAGES, severity=Severity.FLAG, detail=detail, page=page)

    pairs = _paired(source, output, dropped)
    if pairs is None:
        declared = (f"{len(set(dropped))} declared dropped" if dropped is not None
                    else "none declared")
        return [flag(f"source has {len(source.pages)} pages, output {len(output.pages)}; "
                     f"{declared}")]
    out = []
    for source_page, output_page in pairs:
        if abs(source_page.width - output_page.width) > SIZE_TOLERANCE \
                or abs(source_page.height - output_page.height) > SIZE_TOLERANCE:
            out.append(flag(f"size changed from {source_page.width:.0f}x"
                            f"{source_page.height:.0f} (source page {source_page.number}) to "
                            f"{output_page.width:.0f}x{output_page.height:.0f}",
                            output_page.number))
    return out


def _damage(source: PdfFacts, output: PdfFacts, terms: list[str], dropped: list[int] | None,
            removals: list[Removal]) -> list[Finding]:
    """What the source had and the output lost, beyond the builder's names. Run 6
    passed every other check while ten floor plans lost labels like "KITCHEN
    8'0" x 13'0"": nothing compared what was there before."""
    pairs = _paired(source, output, dropped)
    if pairs is None:
        return []  # _pages reports it
    areas: dict[int, list[BBox]] = {}
    for removal in removals:
        if removal.area is not None and removal.page is not None:
            areas.setdefault(removal.page, []).append(removal.area)
    out = []
    for source_page, output_page in pairs:
        lost = _lost_words(source_page, output_page, terms)
        if lost:
            numbered = [word for word in lost if any(char.isdigit() for char in word.text)]
            # A lost dimension or price is lost information; a lost word may be a
            # brand word the hit list does not name, so a person decides.
            out.append(Finding(
                check=Check.DAMAGE, severity=Severity.BLOCK if numbered else Severity.FLAG,
                page=output_page.number,
                detail=f"words gone from source page {source_page.number}: {_listed(lost)}",
                bbox=(numbered or lost)[0].bbox,
            ))
        changed = _changed_outside(source_page, output_page, areas.get(source_page.number, []))
        if changed:
            share, bbox = changed
            out.append(Finding(
                check=Check.DAMAGE, severity=Severity.FLAG, page=output_page.number,
                detail=f"{share:.1%} of source page {source_page.number} looks different outside "
                       "every removal",
                bbox=bbox,
            ))
    return out


def _lost_words(source_page: PageFacts, output_page: PageFacts,
                terms: list[str]) -> list[Word]:
    """Source words missing from the output, except what is meant to go: the
    builder's names and contact details (URLs, emails, phones, domains). Any other
    word counts, whichever tool took it: in run 7 a repair's redact_terms took the
    model name "The Carson" and nothing noticed."""
    words = source_page.words
    text, starts = joined(words)
    expected: set[int] = set()
    matches = [match for term in terms for match in term_pattern(term).finditer(text)]
    matches += [match for pattern in GENERIC.values() for match in pattern.finditer(text)]
    for match in matches:
        expected |= words_in_span(starts, words, match.start(), match.end())
    counted = [word for i, word in enumerate(words) if i not in expected and _word_key(word.text)]
    return missing(counted, output_page.words, key=_word_key)


def _changed_outside(source_page: PageFacts, output_page: PageFacts,
                     areas: list[BBox]) -> tuple[float, BBox] | None:
    """The share of the page whose picture changed outside every removal area and
    the mark's strip, and where, or None when it is under CHANGED_SHARE."""
    before, after = source_page.thumbnail, output_page.thumbnail
    if before is None or after is None or (before.width, before.height) != (
            after.width, after.height):
        return None
    scale = before.width / source_page.width
    masked = bytearray(before.width * before.height)
    mark_strip = (0, source_page.height - MARK_STRIP, source_page.width, source_page.height)
    for x0, y0, x1, y1 in [*areas, mark_strip]:
        left = max(int((x0 - AREA_SLACK) * scale), 0)
        right = min(int((x1 + AREA_SLACK) * scale) + 1, before.width)
        for row in range(max(int((y0 - AREA_SLACK) * scale), 0),
                         min(int((y1 + AREA_SLACK) * scale) + 1, before.height)):
            start = row * before.width
            masked[start + left:start + right] = b"\x01" * max(right - left, 0)
    changed = [i for i, (old, new, hidden) in enumerate(zip(before.gray, after.gray, masked))
               if not hidden and abs(old - new) > PIXEL_CHANGE]
    share = len(changed) / len(masked)
    if share <= CHANGED_SHARE:
        return None
    rows = [i // before.width for i in changed]
    columns = [i % before.width for i in changed]
    return share, (min(columns) / scale, min(rows) / scale,
                   (max(columns) + 1) / scale, (max(rows) + 1) / scale)
