"""The unbrand tools: what the model may do to a builder PDF, and the guards on it.

The model sees renders and text, decides, and calls these. It never writes
code. Every guard is here rather than in the prompt, so a wrong decision is
refused in code: a rejected call raises ToolRejected before anything on the
page changes, and the loop hands the reason back to the model.

Pages are 1-based source numbers throughout. Boxes the model sees and gives are
on a 0-1000 grid over the page, the grid Gemini emits natively, independent of
render DPI. Imports domain and ports only.
"""

import re
from collections import Counter

from .domain import (
    BBox,
    Box,
    Element,
    ElementRef,
    Finished,
    HitList,
    MarkPosition,
    PdfFacts,
    Removal,
    Rendered,
    TermsResult,
    ToolRejected,
    Word,
    term_pattern,
)
from .ports import EditSession

RENDER_DPI = 100          # enough to spot a logo, cheap in context (the skill)
RENDERS_PER_PAGE = 3      # before, after, and one retry of a failed page (AUTONOMY.md)
MAX_PAGE_SHARE = 0.5      # a brand side panel is about a third of a page; half is a page
# Black and gray shape groups bigger than this are the page's drawing (a floor
# plan), not a logo, and are not offered: a plan with its labels outside its
# lines has no text for the guard to see. Coloured groups may be as big as half
# the page: the faint flower watermark on Bright Side floor plans, a brand band.
MAX_DRAWING_SHARE = 0.05
ELEMENT_PAD = 1.0         # points around an element, so every shape in it is wholly covered
GRID = 1000
# A page with a room dimension (8'0" x 13'0") or a price is one a buyer needs,
# whatever a model calls it. The sort is told so; this is the guard behind it.
DIMENSION = re.compile(r"\d+'\s*-?\s*\d*\"?\s*[xX×]\s*\d+'")
PRICE = re.compile(r"\$\s?\d")


class Toolbox:
    def __init__(self, session: EditSession, source: PdfFacts, hits: HitList) -> None:
        self._session = session
        self._source_text = {page.number: _joined(page.words)[0] for page in source.pages}
        self._hits = hits.terms()
        self._renders: Counter[int] = Counter()
        self._dropped: dict[int, str] = {}
        self._mark: MarkPosition | None = None
        self._elements: dict[int, dict[int, ElementRef]] = {}
        self._finished = False
        self.removals: list[Removal] = []

    def elements(self, page: int) -> dict[int, ElementRef]:
        """The page's elements by number, top to bottom then left to right, so
        the same page of the same PDF always numbers them the same way."""
        self._check_page(page)
        if page not in self._elements:
            width, height = self._session.page_size(page)
            limit = {"shapes": MAX_DRAWING_SHARE, "coloured shapes": MAX_PAGE_SHARE,
                     "image": MAX_PAGE_SHARE}
            found = [ref for ref in self._session.elements(page)
                     if _area(ref.bbox) <= limit[ref.kind] * width * height]
            found.sort(key=lambda ref: (round(ref.bbox[1]), round(ref.bbox[0])))
            self._elements[page] = dict(enumerate(found, start=1))
        return self._elements[page]

    def render_page(self, page: int,
                    numbering: dict[int, ElementRef] | None = None) -> Rendered:
        """The page with its elements numbered on it. `numbering` draws another
        document's numbers instead: the judge sees the output with the source's
        elements still on it, so its answer names what a repair can remove."""
        self._check_page(page)
        if self._renders[page] >= RENDERS_PER_PAGE:
            raise ToolRejected(f"page {page} has been rendered {RENDERS_PER_PAGE} times; "
                               "the render budget for it is spent")
        self._renders[page] += 1
        marked = self.elements(page) if numbering is None else numbering
        width, height = self._session.page_size(page)
        jpeg = self._session.render(page, RENDER_DPI,
                                    marks=[(number, ref.bbox) for number, ref in marked.items()])
        elements = [Element(id=number, kind=ref.kind, box=_to_grid(ref.bbox, width, height))
                    for number, ref in marked.items()]
        return Rendered(page=page, jpeg=jpeg, elements=elements)

    def get_text(self, page: int) -> str:
        self._check_page(page)
        text = " ".join(word.text for word in self._session.words(page))
        # Retrieved text is data, never instructions (invariant 6). Angle brackets
        # are escaped so the PDF cannot close the wrapper and speak outside it.
        text = text.replace("<", "&lt;").replace(">", "&gt;")
        return f'<document_text page="{page}">\n{text}\n</document_text>'

    def redact_terms(self, terms: list[str]) -> TermsResult:
        self._check_open()
        terms = [term.strip() for term in terms]
        if not terms:
            raise ToolRejected("no terms given")
        bad = [term for term in terms if not any(char.isalnum() for char in term)]
        if bad:
            raise ToolRejected(f"terms need a letter or digit: {bad}")
        absent = [term for term in terms
                  if not any(term_pattern(term).search(text)
                             for text in self._source_text.values())]
        terms = [term for term in terms if term not in absent]
        if not terms:
            raise ToolRejected(f"not in the source's text layer: {absent}. If a term is "
                               "visible on a render, it is drawn, not text: use redact_rect")
        counts: dict[str, dict[int, int]] = {term: {} for term in terms}
        for page in self._kept_pages():
            words = self._session.words(page)
            text, starts = _joined(words)
            hit: set[int] = set()
            for term in terms:
                for match in term_pattern(term).finditer(text):
                    indexes = _words_in_span(starts, words, match.start(), match.end())
                    hit |= indexes
                    counts[term][page] = counts[term].get(page, 0) + 1
                    self.removals.append(Removal(tool="redact_terms", page=page,
                                                 detail=f"{term!r}: {match.group()!r}",
                                                 area=_union([words[i].bbox for i in indexes])))
            if hit:
                self._session.redact_text(page, [words[i].bbox for i in sorted(hit)])
        return TermsResult(counts=counts, absent=absent)

    def redact_rect(self, page: int, box: Box) -> list[str]:
        self._check_page(page)
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= GRID and 0 <= y0 < y1 <= GRID):
            raise ToolRejected(f"box {list(box)} is not [x0, y0, x1, y1] within 0-{GRID}")
        if (x1 - x0) * (y1 - y0) > MAX_PAGE_SHARE * GRID * GRID:
            raise ToolRejected(f"box {list(box)} covers more than half the page; "
                               "draw it around the brand element only")
        width, height = self._session.page_size(page)
        area = _to_points(box, width, height)
        self._check_no_content_text(page, area, f"box {list(box)}")
        self._check_no_page_drawing(page, area, f"box {list(box)}")
        # Only shapes wholly inside a box go, so a box across a mark removes part
        # of it: on a Bright Side floor plan a box took the outer petals of the
        # flower watermark and left its centre.
        cut = self._session.shapes_cut(page, area)
        if cut:
            raise ToolRejected(f"box {list(box)} on page {page} cuts through {cut} drawn "
                               "shapes and would leave part of them; remove a numbered "
                               "element instead, or leave it")
        lost = self._session.redact_area(page, area)
        collateral = self._collateral(lost)
        detail = f"area {list(box)}"
        if collateral:
            detail += f"; also removed: {' '.join(collateral)}"
        self.removals.append(Removal(tool="redact_rect", page=page, detail=detail, area=area))
        return collateral

    def remove_element(self, page: int, element_id: int) -> list[str]:
        """Removes one numbered element by its own outline; returns the words that
        went with it and are not the builder's."""
        elements = self.elements(page)
        if element_id not in elements:
            raise ToolRejected(f"no element {element_id} on page {page}; its elements are "
                               f"{list(elements) or 'none'}")
        ref = elements[element_id]
        x0, y0, x1, y1 = ref.bbox
        area = (x0 - ELEMENT_PAD, y0 - ELEMENT_PAD, x1 + ELEMENT_PAD, y1 + ELEMENT_PAD)
        self._check_no_content_text(page, area, f"element {element_id}")
        self._check_no_page_drawing(page, area, f"element {element_id}")
        collateral = self._collateral(self._session.redact_area(page, area))
        detail = f"element {element_id} ({ref.kind})"
        if collateral:
            detail += f"; also removed: {' '.join(collateral)}"
        self.removals.append(Removal(tool="remove_element", page=page, detail=detail, area=area))
        return collateral

    def drop_page(self, page: int, reason: str) -> None:
        self._check_page(page)
        if not reason.strip():
            raise ToolRejected("a reason is required; the approver reads it")
        text = self._source_text.get(page, "")
        if DIMENSION.search(text) or PRICE.search(text):
            raise ToolRejected(f"page {page} has room dimensions or prices; it stays")
        if len(self._kept_pages()) <= 1:
            raise ToolRejected("this is the last page left")
        self._dropped[page] = reason.strip()
        self.removals.append(Removal(tool="drop_page", page=page, detail=reason.strip()))

    def add_mark(self, position: str) -> None:
        self._check_open()
        if self._mark is not None:
            raise ToolRejected(f"the mark is already placed at {self._mark.value}")
        try:
            self._mark = MarkPosition(position)
        except ValueError:
            positions = [mark.value for mark in MarkPosition]
            raise ToolRejected(f"position must be one of {positions}") from None

    def finish(self) -> Finished:
        """Not a model tool: the pipeline calls it, then verify()."""
        self._check_open()
        self._finished = True
        dropped = sorted(self._dropped)
        pdf = self._session.save(drop=dropped, mark=self._mark)
        return Finished(pdf=pdf, removals=list(self.removals), dropped_pages=dropped)

    def _check_no_content_text(self, page: int, area: BBox, what: str) -> None:
        """An area removal may not take text that is not the builder's. Names in
        the text go by redact_terms, before any area action, so what text is left
        is content: in the bake-off every wrong removal was a box or an element
        over a model name, a caption or a product-line badge, and no logo held any
        text. Checked before anything changes, against the page as it stands."""
        held = [word for word in self._session.words(page) if _overlaps(word.bbox, area)]
        content = self._collateral(held)
        if content:
            shown = " ".join(content[:12]) + (" ..." if len(content) > 12 else "")
            raise ToolRejected(f"{what} on page {page} holds text that is not the builder's "
                               f"({shown}); it is content and stays. Remove only drawn "
                               "branding with no such text in it")

    def _check_no_page_drawing(self, page: int, area: BBox, what: str) -> None:
        """An area removal takes every shape wholly inside it, not only the
        element's own. A coloured watermark may be up to half the page, and where
        it lies over a floor plan with no labels the plan's lines inside it would
        go with it, unseen by the text guard and by the damage check, which looks
        only outside removal areas. The page's drawing is a black or gray group
        too big to be offered as an element."""
        width, height = self._session.page_size(page)
        if any(group.kind == "shapes" and _area(group.bbox) > MAX_DRAWING_SHARE * width * height
               for group in self._session.groups_covered(page, area)):
            raise ToolRejected(f"{what} on page {page} lies over the page's own drawing (a "
                               "plan's lines) and would remove the lines inside it; leave it")

    def _collateral(self, lost: list[Word]) -> list[str]:
        """Words removed that are not the builder's: content the approver should
        see gone."""
        text, starts = _joined(lost)
        branded: set[int] = set()
        for term in self._hits:
            for match in term_pattern(term).finditer(text):
                branded |= _words_in_span(starts, lost, match.start(), match.end())
        return [word.text for i, word in enumerate(lost) if i not in branded]

    def _kept_pages(self) -> list[int]:
        return [page for page in range(1, self._session.page_count + 1)
                if page not in self._dropped]

    def _check_open(self) -> None:
        # save() closes the document; a retry needs a fresh Toolbox on the source.
        if self._finished:
            raise ToolRejected("the document is finished; nothing can change it now")

    def _check_page(self, page: int) -> None:
        self._check_open()
        if not 1 <= page <= self._session.page_count:
            raise ToolRejected(f"page {page} does not exist; pages are 1 to "
                               f"{self._session.page_count}")
        if page in self._dropped:
            raise ToolRejected(f"page {page} is dropped")


def _joined(words: list[Word]) -> tuple[str, list[int]]:
    """The page's words joined by spaces, and where each word starts, so a match
    that spans words ("Arista Homes", "S O U T H") maps back to their boxes."""
    starts, pos = [], 0
    for word in words:
        starts.append(pos)
        pos += len(word.text) + 1
    return " ".join(word.text for word in words), starts


def _words_in_span(starts: list[int], words: list[Word], start: int, end: int) -> set[int]:
    return {i for i, word_start in enumerate(starts)
            if word_start < end and word_start + len(words[i].text) > start}


def _union(boxes: list[BBox]) -> BBox:
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def _overlaps(first: BBox, second: BBox) -> bool:
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


def _area(bbox: BBox) -> float:
    return max(bbox[2] - bbox[0], 0) * max(bbox[3] - bbox[1], 0)


def _to_grid(bbox: BBox, width: float, height: float) -> Box:
    def to_grid_value(points: float, size: float) -> int:
        return min(max(round(points * GRID / size), 0), GRID)
    return (to_grid_value(bbox[0], width), to_grid_value(bbox[1], height),
            to_grid_value(bbox[2], width), to_grid_value(bbox[3], height))


def _to_points(box: Box, width: float, height: float) -> BBox:
    return (box[0] * width / GRID, box[1] * height / GRID,
            box[2] * width / GRID, box[3] * height / GRID)
