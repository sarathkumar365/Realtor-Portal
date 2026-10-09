"""The unbrand step for one document: sort, pick, apply, judge, repair.

One model reads the whole document once and sorts its pages: which stay, and the
names to take out of the text. For each page that stays, a model is shown the
render with code-found elements numbered on it and picks the ones that are
branding. Code applies everything through the Toolbox guards; verify() and a
model judge look at the result; a model repairs only the pages still wrong, in at
most `max_repair_rounds` repair rounds. No model is asked where anything is.

Every round replays all actions so far on a fresh copy of the source, so a round
is deterministic and safe to repeat (the job worker relies on the same). Elements
are numbered once, on the untouched source, and every round uses that numbering.
"""

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from .domain import (
    EMAIL,
    KEPT_KINDS,
    PHONE,
    PLAN_KINDS,
    Action,
    AddMark,
    Brief,
    DropPage,
    Finding,
    MarkPosition,
    Outcome,
    PageView,
    PdfFacts,
    RedactRect,
    RedactTerms,
    RemoveElement,
    Severity,
    Sorting,
    ToolRejected,
    VerifyReport,
)
from .ports import EditSession, PdfEditor, PdfInspector, UnbrandModels
from .tools import Numbering, Toolbox, number_elements, view_page
from .verify import verify

# Per-page model calls in flight at once. Pages are independent; four keeps one
# document from tripping a provider's rate limit.
PAGE_CONCURRENCY = 4


class RoundResult(BaseModel):
    """One round as it ends, so a caller can keep it before the next one starts."""

    number: int
    pdf: bytes
    outcomes: list[Outcome]
    report: VerifyReport
    judge: list[Finding]
    seconds: dict[str, float]      # apply, verify, judge, repair


class Unbranded(BaseModel):
    pdf: bytes
    sorting: Sorting
    actions: list[Action]
    outcomes: list[Outcome]        # of the last round, one per action
    dropped_pages: list[int]
    report: VerifyReport           # the code checks; `passed` is theirs alone
    judge: list[Finding]           # the model judge, beside the report for the approver
    dropped_steps: list[str]       # model answers left out as malformed, for the approver
    rounds: int                    # rounds applied: the first, plus one per repair round
    plan_seconds: float            # sort and pick, before the first round


@dataclass
class _Rounds:
    """What carries from one round to the next."""

    judged: dict[int, list[Finding]] = field(default_factory=dict)  # by source page, latest
    given_up: set[int] = field(default_factory=set)  # pages no repair is asked for again
    new_from: int = 0  # index of the first action the last repair round added


async def unbrand_document(
    pdf: bytes,
    brief: Brief,
    *,
    editor: PdfEditor,
    inspector: PdfInspector,
    models: UnbrandModels,
    max_repair_rounds: int = 2,
    on_round: Callable[[RoundResult], None] | None = None,
) -> Unbranded:
    if max_repair_rounds < 0:
        raise ValueError(f"max_repair_rounds must be 0 or more, not {max_repair_rounds}")
    # The models' dropped steps from this document only. One models instance
    # serves one document at a time: `dropped` and `usage` are per instance.
    dropped_from = len(models.dropped)
    source = inspector.inspect(pdf, ocr=False)
    pages = list(range(1, brief.page_count + 1))
    started = time.monotonic()
    sorting, actions, numbering = await _plan(pdf, brief, source, pages, editor, models)
    plan_seconds = time.monotonic() - started

    state = _Rounds()
    for number in range(1, max_repair_rounds + 2):
        clock = _Clock()
        session = editor.open(pdf)
        try:
            toolbox = Toolbox(session, source, brief.hits, numbering)
            outcomes = [_apply(toolbox, action) for action in actions]
            done = toolbox.finish()
        finally:
            session.close()
        clock.lap("apply")
        output = inspector.inspect(done.pdf, ocr=True)
        # Removing a sales office address the sort named is not damage.
        report = verify(source, output, brief.hits, dropped_pages=done.dropped_pages,
                        removals=done.removals, removed_terms=sorting.terms)
        clock.lap("verify")

        kept = [page for page in pages if page not in done.dropped_pages]
        new = outcomes[state.new_from:]
        removed = _removed(outcomes)
        repairs: list[Action] = []
        session = editor.open(done.pdf)
        try:
            # A replay changes only the pages the last repair's actions went
            # through; the judge's word on every other page still holds.
            to_judge = kept if number == 1 else _changed(new, kept)
            views = _output_views(session, to_judge, kept, numbering, removed)
            state.judged.update(await _judge(models, brief, views))
            judged = [finding for page in kept for finding in state.judged.get(page, [])]
            clock.lap("judge")

            problems = _problems(report, judged, new, kept)
            if problems and number <= max_repair_rounds:
                if number > 1:
                    state.given_up |= _all_refused(new)
                failing = [page for page in sorted(problems)
                           if page in kept and page not in state.given_up]
                views |= _output_views(session, [page for page in failing if page not in views],
                                       kept, numbering, removed)
                answers = await _repair(models, brief, {page: views[page] for page in failing},
                                        problems)
                # A repair that proposes nothing says nothing can fix the page;
                # asking again got the refused removals back (Bright Side floor plans).
                state.given_up |= {page for page, page_actions in answers.items()
                                   if not page_actions}
                repairs = [action for page_actions in answers.values()
                           for action in page_actions]
                clock.lap("repair")
        finally:
            session.close()

        if on_round:
            on_round(RoundResult(number=number, pdf=done.pdf, outcomes=outcomes, report=report,
                                 judge=judged, seconds=clock.seconds))
        if not repairs:
            break
        state.new_from = len(actions)
        actions += repairs

    return Unbranded(pdf=done.pdf, sorting=sorting, actions=actions, outcomes=outcomes,
                     dropped_pages=done.dropped_pages, report=report, judge=judged,
                     dropped_steps=models.dropped[dropped_from:], rounds=number,
                     plan_seconds=plan_seconds)


async def _plan(pdf: bytes, brief: Brief, source: PdfFacts, pages: list[int],
                editor: PdfEditor, models: UnbrandModels
                ) -> tuple[Sorting, list[Action], Numbering]:
    """The sort and the picks, on the untouched source: what every round applies."""
    session = editor.open(pdf)
    try:
        numbering = {page: number_elements(session, page) for page in pages}
        views = {page: view_page(session, page, numbering[page]) for page in pages}
        sorting = await models.sort(brief, list(views.values()))
        kept = _kept(Toolbox(session, source, brief.hits, numbering),
                     _sorted_actions(sorting, pages), pages)
    finally:
        session.close()
    sorting = _with_contacts(sorting, source, kept)
    actions = _sorted_actions(sorting, pages)
    picked = await _each(kept, lambda page: models.pick(brief, views[page]))
    actions += [action for page_actions in picked for action in page_actions]
    return sorting, actions, numbering


def _output_views(session: EditSession, pages: list[int], kept: list[int],
                  numbering: Numbering, removed: dict[int, set[int]]) -> dict[int, PageView]:
    """Output pages by source page, as the judge and repairs see them: the
    source's elements still there, under their source numbers, so a finding
    names what a repair can remove."""
    views = {}
    for page in pages:
        still_there = {element_id: element for element_id, element in numbering[page].items()
                       if element_id not in removed[page]}
        views[page] = view_page(session, kept.index(page) + 1, still_there, source_page=page)
    return views


async def _judge(models: UnbrandModels, brief: Brief,
                 views: dict[int, PageView]) -> dict[int, list[Finding]]:
    found = await _each(list(views), lambda page: models.judge(brief, views[page]))
    return dict(zip(views, found))


async def _repair(models: UnbrandModels, brief: Brief, views: dict[int, PageView],
                  problems: dict[int, list[str]]) -> dict[int, list[Action]]:
    answers = await _each(list(views),
                          lambda page: models.repair(brief, views[page], problems[page]))
    return dict(zip(views, answers))


def _changed(outcomes: list[Outcome], kept: list[int]) -> list[int]:
    """The kept pages these outcomes went through. An action with no page
    (redact_terms) may change any of them."""
    acted_on = {getattr(outcome.action, "page", None) for outcome in outcomes if outcome.ok}
    return kept if None in acted_on else [page for page in kept if page in acted_on]


def _sorted_actions(sorting: Sorting, pages: list[int]) -> list[Action]:
    """The sorting as actions. A page the sort did not mention stays. A page is
    dropped only when the model said so and its kind is one a buyer does not need:
    keep=False on a floor plan is a contradiction, and the page stays."""
    kinds = {page.page: page for page in sorting.pages}
    out: list[Action] = [DropPage(page=page, why=f"{kinds[page].kind}: {kinds[page].why}")
                         for page in pages
                         if page in kinds and not kinds[page].keep
                         and kinds[page].kind not in KEPT_KINDS]
    if sorting.terms:
        out.append(RedactTerms(terms=sorting.terms, why="names and contact details in the text"))
    kept_kinds = {kinds[page].kind for page in pages if page in kinds and kinds[page].keep}
    position = (MarkPosition.BOTTOM_RIGHT if kept_kinds & PLAN_KINDS or not kept_kinds
                else MarkPosition.BOTTOM_CENTRE)
    out.append(AddMark(position=position, why="Aura Key mark; position by page type"))
    return out


def _with_contacts(sorting: Sorting, source: PdfFacts, kept: list[int]) -> Sorting:
    """The sort's terms plus every phone number and email on a page that stays.
    Code finds these, as the skill's hit list did: on the Bright Side price list
    the sort listed neither the sales office phone nor the email. `kept` is what
    stays once the drops are tried, not what the sort said: a page the guards
    keep needs its contacts gone as much as any other."""
    found = []
    for page in source.pages:
        if page.number in kept:
            text = " ".join(word.text for word in page.words)
            found += [match.group() for pattern in (PHONE, EMAIL)
                      for match in pattern.finditer(text)]
    terms = list(dict.fromkeys(sorting.terms + found))
    return sorting.model_copy(update={"terms": terms})


def _kept(toolbox: Toolbox, actions: list[Action], pages: list[int]) -> list[int]:
    """The pages left once the drops are tried: a guard may refuse one."""
    dropped = {action.page for action in actions
               if isinstance(action, DropPage) and _apply(toolbox, action).ok}
    return [page for page in pages if page not in dropped]


def _removed(outcomes: list[Outcome]) -> dict[int, set[int]]:
    out: dict[int, set[int]] = defaultdict(set)
    for outcome in outcomes:
        if outcome.ok and isinstance(outcome.action, RemoveElement):
            out[outcome.action.page].add(outcome.action.element_id)
    return out


def _all_refused(outcomes: list[Outcome]) -> set[int]:
    """Pages where the guards refused every repair action. Asking again gets the
    same answer: on the Bright Side site plan both repair rounds proposed boxes
    through the gradient horseshoe, and the second round cost about a minute."""
    tried: dict[int, list[bool]] = defaultdict(list)
    for outcome in outcomes:
        page = getattr(outcome.action, "page", None)
        if page is not None:
            tried[page].append(outcome.ok)
    return {page for page, oks in tried.items() if not any(oks)}


async def _each[Answer](pages: list[int],
                        call: Callable[[int], Awaitable[Answer]]) -> list[Answer]:
    """One call per page, a few at a time, answers in page order."""
    gate = asyncio.Semaphore(PAGE_CONCURRENCY)

    async def one(page: int) -> Answer:
        async with gate:
            return await call(page)

    return list(await asyncio.gather(*(one(page) for page in pages)))


class _Clock:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}
        self._last = time.monotonic()

    def lap(self, step: str) -> None:
        now = time.monotonic()
        self.seconds[step] = round(now - self._last, 2)
        self._last = now


def _apply(toolbox: Toolbox, action: Action) -> Outcome:
    try:
        match action:
            case RedactTerms():
                result = toolbox.redact_terms(action.terms)
                detail = "; ".join(f"{term}: {sum(per_page.values())}"
                                   for term, per_page in result.counts.items())
                if result.absent:
                    detail += (f"; not in the text layer: {result.absent}; if visible, "
                               "it is drawn: remove its element")
            case RemoveElement():
                lost = toolbox.remove_element(action.page, action.element_id)
                detail = f"also removed: {' '.join(lost)}" if lost else ""
            case RedactRect():
                lost = toolbox.redact_rect(action.page, action.box)
                detail = f"also removed: {' '.join(lost)}" if lost else ""
            case DropPage():
                toolbox.drop_page(action.page, action.why)
                detail = ""
            case AddMark():
                toolbox.add_mark(action.position)
                detail = ""
    except ToolRejected as error:
        return Outcome(action=action, ok=False, detail=str(error))
    return Outcome(action=action, ok=True, detail=detail)


def _problems(report: VerifyReport, judged: list[Finding], new: list[Outcome],
              kept: list[int]) -> dict[int, list[str]]:
    """What is still wrong, per source page. Findings without a page (metadata,
    raw bytes) cannot be repaired by a page action and stay in the report."""
    out: dict[int, list[str]] = defaultdict(list)
    for finding in report.findings:
        # RETRY only: a BLOCK (a changed number, lost content, OCR not run) is not
        # something a further removal can fix, and goes to a person.
        if finding.severity is Severity.RETRY and finding.page is not None \
                and finding.page <= len(kept):
            out[kept[finding.page - 1]].append(f"{finding.check.value}: {finding.detail}")
    for finding in judged:
        if finding.page is not None and finding.severity is Severity.RETRY:
            out[finding.page].append(f"visible: {finding.detail}")
    for outcome in new:
        page = getattr(outcome.action, "page", None)
        # A refused drop only means the page stays; nothing on it needs repair.
        if not outcome.ok and page is not None and not isinstance(outcome.action, DropPage):
            out[page].append(f"refused {outcome.action.tool}: {outcome.detail}")
    return dict(out)
