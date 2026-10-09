"""In-memory adapter per port, so tests never touch the network.

These exist for the same reason the ports do: if a test needs the real portal
to run, the seam is not real.
"""

import base64
import hashlib
import hmac
import time
from collections.abc import AsyncIterator

from app.capabilities.unbrander.domain import (
    OCR_MODES,
    Action,
    BBox,
    Brief,
    DrawnElement,
    Finding,
    MarkPosition,
    PageFacts,
    PageView,
    PdfFacts,
    Sorting,
    Usage,
    Word,
)
from app.domain import (
    Claims, ChatMode, InventorySummary, Project, ProjectFilters, Role, SearchPage, Tally,
)

TEST_SECRET = "test-secret-not-a-real-key"


def make_token(user: str, role: str = "realtor", *, secret: str = TEST_SECRET,
               issued_ms: int | None = None, gen: str = "abc1234567") -> str:
    """Mint a token the way Core.js makeToken_ does, for tests."""
    issued = issued_ms if issued_ms is not None else int(time.time() * 1000)
    raw = f"{user}|{role}|{gen}|{issued}"
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest()
    ).decode()
    return base64.urlsafe_b64encode(raw.encode()).decode() + "." + sig


class FakeAuthVerifier:
    def __init__(self, claims: Claims | None = None) -> None:
        self.claims = claims or Claims(user="sarath", role=Role.REALTOR, issued_ms=0)
        self.allow = True

    def verify_local(self, token: str) -> Claims | None:
        return self.claims if (self.allow and token) else None

    async def verify(self, token: str) -> Claims | None:
        return self.verify_local(token)


class FakeProjectRepo:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects = projects or []

    async def search(self, filters: ProjectFilters, *, auth: str) -> SearchPage:
        out = self.projects
        if filters.city:
            out = [p for p in out if p.city.upper() == filters.city.upper()]
        if filters.max_price is not None:
            out = [
                p for p in out
                if p.starting_price is not None and p.starting_price <= filters.max_price
            ]
        if filters.categories:
            wanted = set(filters.categories)
            out = [p for p in out if wanted & set(p.categories)]
        if filters.focus_only is not None:
            out = [p for p in out if p.is_focus is filters.focus_only]
        return SearchPage(items=out[: filters.limit], total=len(out))

    async def summarise(self, filters: ProjectFilters, *, auth: str) -> InventorySummary:
        # Reuses this fake's own filtering by asking for everything, so the fake
        # cannot drift into summarising a different set from the one it searches.
        hits = (await self.search(filters.model_copy(update={"limit": 10_000}), auth=auth)).items
        priced = [p for p in hits if p.starting_price is not None]
        counts: dict[str, int] = {}
        for p in hits:
            if p.city:
                counts[p.city] = counts.get(p.city, 0) + 1
        return InventorySummary(
            total=len(hits),
            names=sorted(p.name for p in hits),
            cities=[Tally(label=k, count=n) for k, n in sorted(counts.items())],
            cheapest=min(priced, key=lambda p: p.starting_price, default=None),
            dearest=max(priced, key=lambda p: p.starting_price, default=None),
            without_price=len(hits) - len(priced),
        )

    async def get(self, project_id: str, *, auth: str) -> Project | None:
        exact = next((p for p in self.projects if p.id == project_id), None)
        if exact is not None:
            return exact
        wanted = project_id.casefold()
        return next((p for p in self.projects if p.id.casefold() == wanted), None)

    async def recent(self, days: int, *, auth: str, limit: int = 20) -> list[Project]:
        return self.projects[:limit]

    async def healthy(self) -> bool:
        return True


class FakeConversationStore:
    """In memory, and it enforces the isolation rule rather than assuming it.
    A test that passes here because the fake is permissive would ship a store
    that leaks one realtor's conversations to another."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}
        self.owner: dict[str, str] = {}
        self.heads: dict[str, dict] = {}
        self.feedback: list[dict] = []
        self.up = True                       # flip to make every call raise

    def _live(self) -> None:
        if not self.up:
            raise RuntimeError("connection refused")

    async def create(self, *, user: str, title: str, mode: str = "realtor") -> str:
        self._live()
        cid = f"c{len(self.rows) + 1}"
        self.rows[cid] = []
        self.owner[cid] = user
        self.heads[cid] = {"id": cid, "title": title, "mode": mode, "updated_at": f"t{len(self.rows)}"}
        return cid

    async def append(self, *, conversation_id, role, message, sources=None) -> str:
        self._live()
        mid = f"m{len(self.rows.setdefault(conversation_id, [])) + 1}"
        self.rows[conversation_id].append(
            # id and created_at because the real one returns them: a reopened
            # answer with no id gets no feedback buttons, and a fake that hides
            # that would let the omission ship.
            {
                "id": mid,
                "role": role,
                "message": message,
                "sources": sources or [],
                "created_at": f"t{len(self.rows[conversation_id])}",
            }
        )
        return mid

    async def history(self, *, conversation_id: str, user: str, limit: int = 20) -> list[dict]:
        self._live()
        if self.owner.get(conversation_id) != user:
            return []
        # Windowed like the real one. A fake that returns everything would let a
        # missing LIMIT in the SQL pass every test.
        return self.rows.get(conversation_id, [])[-max(1, limit):]

    async def list_for(self, *, user: str, limit: int = 30) -> list[dict]:
        self._live()
        return [self.heads[c] for c, u in self.owner.items() if u == user][:limit]

    async def meta(self, *, conversation_id: str, user: str) -> dict | None:
        self._live()
        if self.owner.get(conversation_id) != user:
            return None
        return self.heads.get(conversation_id)

    async def set_mode(self, *, conversation_id: str, user: str, mode: str) -> None:
        self._live()
        if self.owner.get(conversation_id) == user:
            self.heads[conversation_id]["mode"] = mode

    async def record_feedback(self, *, user: str, entry: dict) -> None:
        self._live()
        self.feedback.append({**entry, "user_id": user})

    async def list_feedback(self, *, limit: int = 100) -> list[dict]:
        self._live()
        return self.feedback[-limit:]

    async def healthy(self) -> bool:
        return self.up


class FakeDocumentIndex:
    def __init__(self, hits: list[dict] | None = None) -> None:
        self.hits = hits or []

    async def query(self, text, *, project_id=None, client_safe=False, k=5) -> list[dict]:
        return self.hits[:k]

    async def healthy(self) -> bool:
        return True


class FakeAgentRuntime:
    def __init__(self, chunks: list[dict] | None = None) -> None:
        self.chunks = chunks or [{"type": "text", "text": "hello"}]

    async def stream(self, *, question, claims, auth, mode: ChatMode, history) -> AsyncIterator[dict]:
        for c in self.chunks:
            yield c

    async def healthy(self) -> bool:
        return True


class FakePdfInspector:
    """Hands back facts given up front, keyed by the PDF bytes."""

    def __init__(self, facts: dict[bytes, PdfFacts]) -> None:
        self.facts = facts
        self.calls: list[tuple[bytes, bool]] = []

    def inspect(self, pdf: bytes, *, ocr: bool) -> PdfFacts:
        self.calls.append((pdf, ocr))
        return self.facts[pdf]


class FakeEditSession:
    """Pages as word lists and element lists. Redaction removes the words whose
    box it was given or that sit inside the area; every call is logged."""

    def __init__(self, pages: list[list[Word]],
                 elements: dict[int, list[DrawnElement]] | None = None,
                 size: tuple[float, float] = (612, 792)) -> None:
        self.pages = [list(p) for p in pages]
        self.element_map = elements or {}
        self.size = size
        self.page_count = len(pages)
        self.calls: list[tuple] = []
        self.closed = False

    def page_size(self, page: int) -> tuple[float, float]:
        return self.size

    def words(self, page: int) -> list[Word]:
        return list(self.pages[page - 1])

    def elements(self, page: int) -> list[DrawnElement]:
        return list(self.element_map.get(page, []))

    def groups_covered(self, page: int, box: BBox) -> list[DrawnElement]:
        """Elements the box overlaps: each stands for a group of many drawings,
        some of which may lie inside the box."""
        return [ref for ref in self.element_map.get(page, [])
                if ref.bbox[0] < box[2] and box[0] < ref.bbox[2]
                and ref.bbox[1] < box[3] and box[1] < ref.bbox[3]]

    def shapes_cut(self, page: int, box: BBox) -> int:
        """Elements the box overlaps without covering."""
        def overlaps(ref: DrawnElement) -> bool:
            return (ref.bbox[0] < box[2] and box[0] < ref.bbox[2]
                    and ref.bbox[1] < box[3] and box[1] < ref.bbox[3])
        def covered(ref: DrawnElement) -> bool:
            return (box[0] <= ref.bbox[0] and box[1] <= ref.bbox[1]
                    and ref.bbox[2] <= box[2] and ref.bbox[3] <= box[3])
        return sum(1 for ref in self.element_map.get(page, []) if overlaps(ref) and not covered(ref))

    def render(self, page: int, dpi: int, marks: list[tuple[int, BBox]] | None = None) -> bytes:
        self.calls.append(("render", page, dpi, marks))
        return b"jpeg"

    def redact_text(self, page: int, boxes: list[BBox]) -> None:
        self.calls.append(("redact_text", page, boxes))
        self.pages[page - 1] = [w for w in self.pages[page - 1] if w.bbox not in boxes]

    def redact_area(self, page: int, box: BBox) -> list[Word]:
        self.calls.append(("redact_area", page, box))
        def inside(w: Word) -> bool:
            return (w.bbox[0] >= box[0] and w.bbox[1] >= box[1]
                    and w.bbox[2] <= box[2] and w.bbox[3] <= box[3])
        lost = [w for w in self.pages[page - 1] if inside(w)]
        self.pages[page - 1] = [w for w in self.pages[page - 1] if not inside(w)]
        return lost

    def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
        self.calls.append(("save", drop, mark))
        self.closed = True
        return b"%PDF-fake"

    def close(self) -> None:
        self.calls.append(("close",))
        self.closed = True


class FakePdfEditor:
    def __init__(self, session: FakeEditSession) -> None:
        self.session = session

    def open(self, pdf: bytes) -> FakeEditSession:
        return self.session


class FakePdfStore:
    """PdfEditor and PdfInspector at once, over PDFs held as word lists by their
    bytes. Every open() starts from what is stored, and save() stores a new PDF,
    so a pipeline can replay from the source and inspect what it saved."""

    def __init__(self, source: bytes, pages: list[list[Word]],
                 elements: dict[int, list[DrawnElement]] | None = None) -> None:
        self.source = source
        self.docs: dict[bytes, list[list[Word]]] = {source: pages}
        self.elements = elements or {}
        self.opened: list[bytes] = []
        self.sessions: list[FakeEditSession] = []

    def open(self, pdf: bytes) -> FakeEditSession:
        self.opened.append(pdf)
        store = self

        class Session(FakeEditSession):
            def save(self, *, drop: list[int], mark: MarkPosition | None) -> bytes:
                super().save(drop=drop, mark=mark)
                out = f"out-{len(store.docs)}".encode()
                store.docs[out] = [page for i, page in enumerate(self.pages, 1) if i not in drop]
                return out

        session = Session(self.docs[pdf],
                          elements=self.elements if pdf == self.source else {})
        self.sessions.append(session)
        return session

    def inspect(self, pdf: bytes, *, ocr: bool) -> PdfFacts:
        pages = []
        for number, words in enumerate(self.docs[pdf], 1):
            text = " ".join(word.text for word in words)
            pages.append(PageFacts(number=number, width=612, height=792, words=words,
                                   ocr={mode: text for mode in OCR_MODES} if ocr else {}))
        return PdfFacts(pages=pages)


class FakeUnbrandModels:
    """Scripted sort, pick, judge and repair. `pick` and `repair` map a source page
    to the actions they return. `judge` is called with how many times that page
    has been judged (1 in the first round) and the page it is shown."""

    def __init__(self, sorting: Sorting, *, pick: dict[int, list[Action]] | None = None,
                 judge=None, repair: dict[int, list[Action]] | None = None) -> None:
        self._sorting = sorting
        self._pick = pick or {}
        self._judge = judge or (lambda round_number, page: [])
        self._repair = repair or {}
        self.usage = {role: Usage() for role in ("sort", "pick", "judge", "repair")}
        self.dropped: list[str] = []
        self.briefs: list[Brief] = []
        self.picked: list[int] = []
        self.judged: list[int] = []
        self.judge_views: list[PageView] = []
        self.repaired: list[tuple[int, list[str]]] = []

    async def sort(self, brief: Brief, pages: list[PageView]) -> Sorting:
        self.briefs.append(brief)
        return self._sorting

    async def pick(self, brief: Brief, page: PageView) -> list:
        self.picked.append(page.page)
        return list(self._pick.get(page.page, []))

    async def judge(self, brief: Brief, page: PageView) -> list[Finding]:
        self.judged.append(page.page)
        self.judge_views.append(page)
        return self._judge(self.judged.count(page.page), page)

    async def repair(self, brief: Brief, page: PageView, problems: list[str]) -> list[Action]:
        self.repaired.append((page.page, problems))
        return list(self._repair.get(page.page, []))
