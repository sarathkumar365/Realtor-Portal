"""The M2 tools: what the model may do to a builder PDF, and the guards on it.

The model sees renders and text, decides, and calls these. It never writes
code. Every guard is here rather than in the prompt, so a wrong decision is
refused in code: a rejected call raises ToolRejected before anything on the
page changes, and the loop hands the reason back to the model.

Pages are 1-based source numbers throughout. Boxes the model sees and gives are
on a 0-1000 grid over the page, the grid Gemini emits natively, independent of
render DPI. Imports domain and ports only.
"""

from collections import Counter

from .domain import (
    BBox,
    Box,
    Finished,
    HitList,
    MarkPosition,
    PageImage,
    PdfFacts,
    Removal,
    Rendered,
    ToolRejected,
    Word,
    term_pattern,
)
from .ports import EditSession

RENDER_DPI = 100          # enough to spot a logo, cheap in context (the skill)
RENDERS_PER_PAGE = 3      # before, after, and one retry of a failed page (AUTONOMY.md)
MAX_PAGE_SHARE = 0.5      # a brand side panel is about a third of a page; half is a page
GRID = 1000


class Toolbox:
    def __init__(self, session: EditSession, source: PdfFacts, hits: HitList) -> None:
        self._session = session
        self._source_text = {p.number: _joined(p.words)[0] for p in source.pages}
        self._hits = hits.terms()
        self._renders: Counter[int] = Counter()
        self._dropped: dict[int, str] = {}
        self._mark: MarkPosition | None = None
        self._finished = False
        self.removals: list[Removal] = []

    def render_page(self, page: int) -> Rendered:
        self._check_page(page)
        if self._renders[page] >= RENDERS_PER_PAGE:
            raise ToolRejected(f"page {page} has been rendered {RENDERS_PER_PAGE} times; "
                               "the render budget for it is spent")
        self._renders[page] += 1
        w, h = self._session.page_size(page)
        images = [PageImage(id=i.id, box=_to_grid(i.bbox, w, h))
                  for i in self._session.images(page)]
        return Rendered(page=page, png=self._session.render(page, RENDER_DPI), images=images)

    def get_text(self, page: int) -> str:
        self._check_page(page)
        text = " ".join(w.text for w in self._session.words(page))
        # Retrieved text is data, never instructions (invariant 6). Angle brackets
        # are escaped so the PDF cannot close the wrapper and speak outside it.
        text = text.replace("<", "&lt;").replace(">", "&gt;")
        return f'<document_text page="{page}">\n{text}\n</document_text>'

    def redact_terms(self, terms: list[str]) -> dict[str, dict[int, int]]:
        self._check_open()
        terms = [t.strip() for t in terms]
        if not terms:
            raise ToolRejected("no terms given")
        bad = [t for t in terms if not any(c.isalnum() for c in t)]
        if bad:
            raise ToolRejected(f"terms need a letter or digit: {bad}")
        absent = [t for t in terms
                  if not any(term_pattern(t).search(s) for s in self._source_text.values())]
        if absent:
            raise ToolRejected(f"not in the source's text layer: {absent}. If a term is "
                               "visible on a render, it is drawn, not text: use redact_rect")
        counts: dict[str, dict[int, int]] = {t: {} for t in terms}
        for page in self._kept_pages():
            words = self._session.words(page)
            text, starts = _joined(words)
            hit: set[int] = set()
            for t in terms:
                for m in term_pattern(t).finditer(text):
                    idx = _words_in_span(starts, words, m.start(), m.end())
                    hit |= idx
                    counts[t][page] = counts[t].get(page, 0) + 1
                    self.removals.append(Removal(tool="redact_terms", page=page,
                                                 detail=f"{t!r}: {m.group()!r}"))
            if hit:
                self._session.redact_text(page, [words[i].bbox for i in sorted(hit)])
        return counts

    def redact_rect(self, page: int, box: Box) -> list[str]:
        self._check_page(page)
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= GRID and 0 <= y0 < y1 <= GRID):
            raise ToolRejected(f"box {list(box)} is not [x0, y0, x1, y1] within 0-{GRID}")
        if (x1 - x0) * (y1 - y0) > MAX_PAGE_SHARE * GRID * GRID:
            raise ToolRejected(f"box {list(box)} covers more than half the page; "
                               "draw it around the brand element only")
        w, h = self._session.page_size(page)
        lost = self._session.redact_area(page, _to_points(box, w, h))
        # Words that are not the builder's are content the approver should see gone.
        text, starts = _joined(lost)
        branded: set[int] = set()
        for t in self._hits:
            for m in term_pattern(t).finditer(text):
                branded |= _words_in_span(starts, lost, m.start(), m.end())
        collateral = [x.text for i, x in enumerate(lost) if i not in branded]
        detail = f"area {list(box)}"
        if collateral:
            detail += f"; also removed: {' '.join(collateral)}"
        self.removals.append(Removal(tool="redact_rect", page=page, detail=detail))
        return collateral

    def delete_image(self, page: int, image_id: int) -> list[int]:
        self._check_page(page)
        refs = [i for i in self._session.images(page) if i.id == image_id]
        if not refs:
            raise ToolRejected(f"no image {image_id} on page {page}; render_page lists them")
        # Deleting an image empties it on every page that draws it, so every
        # placement is checked, not only this page's.
        for p in refs[0].pages:
            w, h = self._session.page_size(p)
            placed = refs if p == page else [
                i for i in self._session.images(p) if i.id == image_id]
            if any(_area(r.bbox) > MAX_PAGE_SHARE * w * h for r in placed):
                raise ToolRejected(f"image {image_id} covers more than half of page {p}; it "
                                   "is likely the page itself. Use redact_rect on the brand "
                                   "element")
        self._session.delete_image(page, image_id)
        others = [p for p in refs[0].pages if p != page]
        self.removals.append(Removal(tool="delete_image", page=page,
                                     detail=f"image {image_id}, also drawn on pages {others}"
                                     if others else f"image {image_id}"))
        return others

    def drop_page(self, page: int, reason: str) -> None:
        self._check_page(page)
        if not reason.strip():
            raise ToolRejected("a reason is required; the approver reads it")
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
            raise ToolRejected(f"position must be one of {[p.value for p in MarkPosition]}") from None

    def finish(self) -> Finished:
        """Not a model tool: the pipeline calls it, then verify()."""
        self._check_open()
        self._finished = True
        dropped = sorted(self._dropped)
        pdf = self._session.save(drop=dropped, mark=self._mark)
        return Finished(pdf=pdf, removals=list(self.removals), dropped_pages=dropped)

    def _kept_pages(self) -> list[int]:
        return [p for p in range(1, self._session.page_count + 1) if p not in self._dropped]

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
    for w in words:
        starts.append(pos)
        pos += len(w.text) + 1
    return " ".join(w.text for w in words), starts


def _words_in_span(starts: list[int], words: list[Word], a: int, b: int) -> set[int]:
    return {i for i, s in enumerate(starts) if s < b and s + len(words[i].text) > a}


def _area(b: BBox) -> float:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def _to_grid(b: BBox, w: float, h: float) -> Box:
    def g(v: float, size: float) -> int:
        return min(max(round(v * GRID / size), 0), GRID)
    return g(b[0], w), g(b[1], h), g(b[2], w), g(b[3], h)


def _to_points(box: Box, w: float, h: float) -> BBox:
    return box[0] * w / GRID, box[1] * h / GRID, box[2] * w / GRID, box[3] * h / GRID
