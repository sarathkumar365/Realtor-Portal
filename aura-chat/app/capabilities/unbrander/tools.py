"""The unbrand tools: what may be done to a builder PDF, and the guards on it.

A model decides; code applies its decisions through these. It never writes code
or calls them itself. Every guard is here rather than in a prompt, so a wrong
decision is refused in code: a refused call raises ToolRejected before anything
on the page changes, and the reason goes back to the model with the next repair.

Pages are 1-based source numbers throughout. Boxes a model sees and gives are on
a 0-1000 grid over the page, the grid Gemini emits natively, independent of
render DPI. Imports domain and ports only.
"""

import re

from .domain import (
    BBox,
    DrawnElement,
    Finished,
    GridBox,
    HitList,
    MarkPosition,
    NumberedElement,
    PageView,
    PdfFacts,
    Removal,
    TermsResult,
    ToolRejected,
    Word,
    area,
    intersects,
    joined,
    term_pattern,
    to_box_2d,
    union,
    words_in_span,
)
from .ports import EditSession

RENDER_DPI = 100          # enough to spot a logo, cheap in context (the skill)
MAX_PAGE_SHARE = 0.5      # a brand side panel is about a third of a page; half is a page
# Black and gray shape groups bigger than this are the page's drawing (a floor
# plan), not a logo, and are not offered: a plan with its labels outside its
# lines has no text for the guard to see. Coloured groups may be as big as half
# the page: the faint flower watermark on Bright Side floor plans, a brand band.
MAX_DRAWING_SHARE = 0.05
ELEMENT_PAD = 1.0         # points around an element, so every shape in it is wholly covered
GRID = 1000
LISTED_WORDS = 12         # content words quoted in a refusal; the rest are counted
# A page with a room dimension (8'0" x 13'0") or a price is one a buyer needs,
# whatever a model calls it. The sort is told so; this is the guard behind it.
DIMENSION = re.compile(r"\d+'\s*-?\s*\d*\"?\s*[xX×]\s*\d+'")
PRICE = re.compile(r"\$\s?\d")

Numbering = dict[int, dict[int, DrawnElement]]  # page -> element number -> element


def number_elements(session: EditSession, page: int) -> dict[int, DrawnElement]:
    """The elements a model may pick on a page, by number, top to bottom then
    left to right. Numbered once, on the untouched source: removing text rewrites
    a page's drawing commands, and numbering again after it renumbered a Bright
    Side floor plan (13 elements became 15), so a picked number named another
    element."""
    width, height = session.page_size(page)
    limit = {"shapes": MAX_DRAWING_SHARE, "coloured shapes": MAX_PAGE_SHARE,
             "image": MAX_PAGE_SHARE}
    found = [element for element in session.elements(page)
             if area(element.bbox) <= limit[element.kind] * width * height]
    found.sort(key=lambda element: (round(element.bbox[1]), round(element.bbox[0])))
    return dict(enumerate(found, start=1))


def view_page(session: EditSession, page: int, elements: dict[int, DrawnElement], *,
              source_page: int | None = None) -> PageView:
    """The page as a model sees it: the render with each element's number drawn
    on it, the elements on the grid, and the text wrapped as data. `page` is the
    session's page; `source_page` is the number the model is told, when the
    session is an output with pages dropped."""
    if not 1 <= page <= session.page_count:
        # Not a model's mistake but a caller's: a pymupdf session reads page 0
        # as the last page and would show it under the wrong number.
        raise ValueError(f"page {page} is outside 1-{session.page_count}")
    number = page if source_page is None else source_page
    width, height = session.page_size(page)
    jpeg = session.render(page, RENDER_DPI,
                          marks=[(element_id, element.bbox)
                                 for element_id, element in elements.items()])
    numbered = [NumberedElement(id=element_id, kind=element.kind,
                                box=_to_grid(element.bbox, width, height))
                for element_id, element in elements.items()]
    text = " ".join(word.text for word in session.words(page))
    # Retrieved text is data, never instructions (invariant 6). Angle brackets
    # are escaped so the PDF cannot close the wrapper and speak outside it.
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return PageView(page=number, jpeg=jpeg, elements=numbered,
                    text=f'<document_text page="{number}">\n{text}\n</document_text>')


class Toolbox:
    """The guarded edits on one PDF. `elements` is the source's numbering, from
    number_elements(); every round of a document gets the same one."""

    def __init__(self, session: EditSession, source: PdfFacts, hits: HitList,
                 elements: Numbering) -> None:
        self._session = session
        self._source_text = {page.number: joined(page.words)[0] for page in source.pages}
        self._hits = hits.terms()
        self._elements = elements
        self._dropped: dict[int, str] = {}
        self._mark: MarkPosition | None = None
        self._finished = False
        self.removals: list[Removal] = []

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
            text, starts = joined(words)
            hit: set[int] = set()
            for term in terms:
                for match in term_pattern(term).finditer(text):
                    indexes = words_in_span(starts, words, match.start(), match.end())
                    hit |= indexes
                    counts[term][page] = counts[term].get(page, 0) + 1
                    self.removals.append(Removal(tool="redact_terms", page=page,
                                                 detail=f"{term!r}: {match.group()!r}",
                                                 area=union([words[i].bbox for i in indexes])))
            if hit:
                self._session.redact_text(page, [words[i].bbox for i in sorted(hit)])
        return TermsResult(counts=counts, absent=absent)

    def redact_rect(self, page: int, box: GridBox) -> list[str]:
        """`box` is x first. Refusals quote it as box_2d, the order the model
        gave it in, so a repair that proposed several boxes knows which failed."""
        self._check_page(page)
        x0, y0, x1, y1 = box
        named = f"box_2d {to_box_2d(box)}"
        if not (0 <= x0 < x1 <= GRID and 0 <= y0 < y1 <= GRID):
            raise ToolRejected(f"{named} is not inside the 0-{GRID} grid, or has no width "
                               "or height")
        if (x1 - x0) * (y1 - y0) > MAX_PAGE_SHARE * GRID * GRID:
            raise ToolRejected(f"{named} covers more than half the page; "
                               "draw it around the brand element only")
        width, height = self._session.page_size(page)
        covered = _to_points(box, width, height)
        self._check_no_content_text(page, covered, named)
        self._check_no_page_drawing(page, covered, named)
        # Only shapes wholly inside a box go, so a box across a mark removes part
        # of it: on a Bright Side floor plan a box took the outer petals of the
        # flower watermark and left its centre.
        cut = self._session.shapes_cut(page, covered)
        if cut:
            raise ToolRejected(f"{named} on page {page} cuts through {cut} drawn "
                               "shapes and would leave part of them; remove a numbered "
                               "element instead, or leave it")
        lost = self._session.redact_area(page, covered)
        collateral = self._collateral(lost)
        detail = f"area {named}"
        if collateral:
            detail += f"; also removed: {' '.join(collateral)}"
        self.removals.append(Removal(tool="redact_rect", page=page, detail=detail,
                                     area=covered))
        return collateral

    def remove_element(self, page: int, element_id: int) -> list[str]:
        """Removes one numbered element by its own outline; returns the words that
        went with it and are not the builder's."""
        self._check_page(page)
        elements = self._elements.get(page, {})
        if element_id not in elements:
            raise ToolRejected(f"no element {element_id} on page {page}; its elements are "
                               f"{list(elements) or 'none'}")
        element = elements[element_id]
        x0, y0, x1, y1 = element.bbox
        covered = (x0 - ELEMENT_PAD, y0 - ELEMENT_PAD, x1 + ELEMENT_PAD, y1 + ELEMENT_PAD)
        self._check_no_content_text(page, covered, f"element {element_id}")
        self._check_no_page_drawing(page, covered, f"element {element_id}")
        collateral = self._collateral(self._session.redact_area(page, covered))
        detail = f"element {element_id} ({element.kind})"
        if collateral:
            detail += f"; also removed: {' '.join(collateral)}"
        self.removals.append(Removal(tool="remove_element", page=page, detail=detail,
                                     area=covered))
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

    def _check_no_content_text(self, page: int, covered: BBox, what: str) -> None:
        """An area removal may not take text that is not the builder's. Names in
        the text go by redact_terms, before any area action, so what text is left
        is content: in the bake-off every wrong removal was a box or an element
        over a model name, a caption or a product-line badge, and no logo held any
        text. Checked before anything changes, against the page as it stands."""
        held = [word for word in self._session.words(page) if intersects(word.bbox, covered)]
        content = self._collateral(held)
        if content:
            shown = " ".join(content[:LISTED_WORDS]) + (" ..." if len(content) > LISTED_WORDS
                                                         else "")
            raise ToolRejected(f"{what} on page {page} holds text that is not the builder's "
                               f"({shown}); it is content and stays. Remove only drawn "
                               "branding with no such text in it")

    def _check_no_page_drawing(self, page: int, covered: BBox, what: str) -> None:
        """An area removal takes every shape wholly inside it, not only the
        element's own. A coloured watermark may be up to half the page, and where
        it lies over a floor plan with no labels the plan's lines inside it would
        go with it, unseen by the text guard and by the damage check, which looks
        only outside removal areas. The page's drawing is a black or gray group
        too big to be offered as an element."""
        width, height = self._session.page_size(page)
        if any(group.kind == "shapes" and area(group.bbox) > MAX_DRAWING_SHARE * width * height
               for group in self._session.groups_covered(page, covered)):
            raise ToolRejected(f"{what} on page {page} lies over the page's own drawing (a "
                               "plan's lines) and would remove the lines inside it; leave it")

    def _collateral(self, lost: list[Word]) -> list[str]:
        """Words removed that are not the builder's: content the approver should
        see gone."""
        text, starts = joined(lost)
        branded: set[int] = set()
        for term in self._hits:
            for match in term_pattern(term).finditer(text):
                branded |= words_in_span(starts, lost, match.start(), match.end())
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


def _to_grid(bbox: BBox, width: float, height: float) -> GridBox:
    def to_grid_value(points: float, size: float) -> int:
        return min(max(round(points * GRID / size), 0), GRID)
    return (to_grid_value(bbox[0], width), to_grid_value(bbox[1], height),
            to_grid_value(bbox[2], width), to_grid_value(bbox[3], height))


def _to_points(box: GridBox, width: float, height: float) -> BBox:
    return (box[0] * width / GRID, box[1] * height / GRID,
            box[2] * width / GRID, box[3] * height / GRID)
