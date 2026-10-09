"""The unbrand step's sort, pick, execute, judge and repair loop, on in-memory PDFs
and scripted models."""

import asyncio

import pytest

from app.capabilities.unbrander.domain import (
    AddMark,
    Brief,
    Check,
    DrawnElement,
    DropPage,
    Finding,
    HitList,
    MarkPosition,
    PageSort,
    RedactRect,
    RedactTerms,
    RemoveElement,
    Severity,
    Sorting,
    Word,
)
from app.capabilities.unbrander.unbrand import RoundResult, unbrand_document
from tests.fakes import FakePdfStore, FakeUnbrandModels

SOURCE = b"source"
HITS = HitList(builder="Arista Homes", project="SouthCal")


def words(text: str, top: float = 100) -> list[Word]:
    out, left = [], 50.0
    for token in text.split():
        out.append(Word(text=token, bbox=(left, top, left + 10 * len(token), top + 12)))
        left += 10 * len(token) + 5
    return out


def store(*pages: str, elements=None) -> FakePdfStore:
    return FakePdfStore(SOURCE, [words(page) for page in pages], elements=elements)


def brief(page_count: int, instructions: str | None = None) -> Brief:
    return Brief(hits=HITS, page_count=page_count, instructions=instructions)


def texts(pdfs: FakePdfStore, pdf: bytes) -> list[str]:
    return [" ".join(word.text for word in page) for page in pdfs.docs[pdf]]


def sorting(*kinds: str, terms=("SouthCal",)) -> Sorting:
    return Sorting(pages=[PageSort(page=page, kind=kind, keep=kind != "marketing", why=kind)
                          for page, kind in enumerate(kinds, start=1)], terms=list(terms))


def leak(page: int) -> Finding:
    return Finding(check=Check.VISUAL, severity=Severity.RETRY, page=page, detail="logo")


async def run(pdfs, models, page_count, **options):
    instructions = options.pop("instructions", None)
    return await unbrand_document(SOURCE, brief(page_count, instructions), editor=pdfs,
                                  inspector=pdfs, models=models, **options)


async def test_the_sort_drops_marketing_removes_terms_and_places_the_mark():
    pdfs = store("SouthCal cover", "SouthCal Lot 12", "Model A")
    models = FakeUnbrandModels(sorting("marketing", "floor_plan", "elevation"))
    done = await run(pdfs, models, 3)
    assert done.dropped_pages == [1]
    assert texts(pdfs, done.pdf) == ["Lot 12", "Model A"]
    assert done.actions[-1] == AddMark(position=MarkPosition.BOTTOM_RIGHT,
                                       why="Aura Key mark; position by page type")
    assert models.picked == [2, 3]  # dropped pages are never picked
    assert done.report.passed and done.rounds == 1


async def test_text_pages_get_the_mark_bottom_centre():
    models = FakeUnbrandModels(sorting("feature_sheet", terms=()))
    done = await run(store("Granite 9' ceilings"), models, 1)
    assert done.actions == [AddMark(position=MarkPosition.BOTTOM_CENTRE,
                                    why="Aura Key mark; position by page type")]


async def test_a_page_with_dimensions_is_not_dropped_whatever_the_sort_says():
    pdfs = store("cover", "KITCHEN 8'0\" x 13'0\"")
    models = FakeUnbrandModels(sorting("marketing", "marketing", terms=()))
    done = await run(pdfs, models, 2)
    assert done.dropped_pages == [1]
    assert models.picked == [2] and models.repaired == []
    refused = [outcome for outcome in done.outcomes if not outcome.ok]
    assert "dimensions" in refused[0].detail


async def test_keep_false_on_a_kind_buyers_need_is_ignored():
    models = FakeUnbrandModels(Sorting(pages=[
        PageSort(page=1, kind="floor_plan", keep=False, why="contradiction"),
        PageSort(page=2, kind="marketing", keep=False, why="cover")], terms=[]))
    done = await run(store("plan", "cover"), models, 2)
    assert done.dropped_pages == [2]


async def test_picked_elements_are_removed_by_their_outline():
    logo = DrawnElement(kind="shapes", bbox=(40, 90, 290, 120))
    pdfs = store("SouthCal Arista Homes", elements={1: [logo]})
    pick = {1: [RemoveElement(page=1, element_id=1, why="logo")]}
    models = FakeUnbrandModels(sorting("floor_plan", terms=()), pick=pick)
    done = await run(pdfs, models, 1)
    assert texts(pdfs, done.pdf) == [""]
    assert [outcome.ok for outcome in done.outcomes] == [True, True]


async def test_the_judge_sees_only_the_elements_still_there_with_source_numbers():
    elements = {2: [DrawnElement(kind="image", bbox=(10, 10, 60, 40)),
                    DrawnElement(kind="shapes", bbox=(400, 700, 500, 740))]}
    pdfs = store("cover", "Lot 12", elements=elements)
    pick = {2: [RemoveElement(page=2, element_id=1, why="logo")]}
    models = FakeUnbrandModels(sorting("marketing", "floor_plan", terms=()), pick=pick)
    await run(pdfs, models, 2)
    [view] = models.judge_views
    assert view.page == 2 and [element.id for element in view.elements] == [2]


async def test_a_finding_on_one_page_repairs_that_page_only():
    pdfs = store("SouthCal a", "b", "c")
    fix = RedactRect(page=3, box=(0, 0, 100, 100), why="logo")
    models = FakeUnbrandModels(sorting("floor_plan", "floor_plan", "floor_plan"),
                               judge=lambda round_number, page: [leak(3)]
                               if page.page == 3 and round_number == 1 else [],
                               repair={3: [fix]})
    done = await run(pdfs, models, 3)
    assert [page for page, _ in models.repaired] == [3]
    assert models.repaired[0][1] == ["visible: logo"]
    assert done.rounds == 2 and done.actions[-1] == fix
    assert sorted(models.judged) == [1, 2, 3, 3]  # pages 1 and 2 did not change


async def test_repair_stops_after_max_repair_rounds():
    pdfs = store("SouthCal a")
    fix = RedactRect(page=1, box=(0, 0, 100, 100), why="logo")
    models = FakeUnbrandModels(sorting("floor_plan"), judge=lambda round_number, page: [leak(1)],
                               repair={1: [fix]})
    done = await run(pdfs, models, 1, max_repair_rounds=2)
    assert len(models.repaired) == 2 and done.rounds == 3
    assert done.judge == [leak(1)]


async def test_a_page_whose_repairs_were_all_refused_is_not_repaired_again():
    """Bright Side site plan: the second repair round proposed the same refused
    boxes, at the cost of another apply, OCR and judge pass."""
    pdfs = store("SouthCal a", "Lot 12")
    refused = RedactRect(page=2, box=(0, 0, 1000, 400), why="logo over the lot number")
    models = FakeUnbrandModels(sorting("floor_plan", "floor_plan"),
                               judge=lambda round_number, page: [leak(page.page)],
                               repair={1: [RedactRect(page=1, box=(0, 0, 100, 100), why="logo")],
                                       2: [refused]})
    done = await run(pdfs, models, 2, max_repair_rounds=2)
    assert [page for page, _ in models.repaired] == [1, 2, 1]
    assert done.rounds == 3 and leak(2) in done.judge


async def test_a_page_given_up_on_ends_the_rounds_when_no_other_page_needs_work():
    pdfs = store("Lot 12")
    refused = RedactRect(page=1, box=(0, 0, 1000, 400), why="logo over the lot number")
    models = FakeUnbrandModels(sorting("floor_plan", terms=()),
                               judge=lambda round_number, page: [leak(1)], repair={1: [refused]})
    done = await run(pdfs, models, 1, max_repair_rounds=5)
    assert len(models.repaired) == 1 and done.rounds == 2


async def test_the_judge_never_decides_passed():
    models = FakeUnbrandModels(sorting("floor_plan"), judge=lambda round_number, page: [leak(1)])
    done = await run(store("SouthCal a"), models, 1, max_repair_rounds=0)
    assert done.report.passed and done.judge


async def test_every_round_replays_from_the_source():
    pdfs = store("SouthCal a b")
    fix = RedactTerms(terms=["a"], why="leftover")
    models = FakeUnbrandModels(sorting("floor_plan"),
                               judge=lambda round_number, page: [leak(1)]
                               if round_number == 1 else [],
                               repair={1: [fix]})
    done = await run(pdfs, models, 1)
    sources = [pdf for pdf in pdfs.opened if pdf == SOURCE]
    assert len(sources) == 3  # the plan (views and drop check), round 1, round 2
    assert texts(pdfs, done.pdf) == ["b"]


async def test_a_code_finding_maps_back_to_its_source_page_after_a_drop():
    pdfs = store("cover", "plan", "SouthCal drawn")
    models = FakeUnbrandModels(sorting("marketing", "floor_plan", "floor_plan",
                                       terms=["drawn"]))
    done = await run(pdfs, models, 3, max_repair_rounds=1)
    assert done.dropped_pages == [1]
    assert [page for page, _ in models.repaired] == [3]
    assert models.repaired[0][1][0].startswith("text_sweep")
    assert sorted(models.judged[:2]) == [2, 3]


async def test_an_absent_term_is_reported_and_the_others_still_go():
    pdfs = store("SouthCal by Arista Homes")
    models = FakeUnbrandModels(sorting("floor_plan",
                                       terms=["SouthCal", "Arista Homes", "ARISTA’s"]))
    done = await run(pdfs, models, 1)
    assert texts(pdfs, done.pdf) == ["by"]
    assert "not in the text layer: ['ARISTA’s']" in done.outcomes[0].detail


async def test_the_operators_instructions_reach_the_sort():
    models = FakeUnbrandModels(sorting("floor_plan"))
    await run(store("SouthCal"), models, 1, instructions="drop the sales centre map")
    assert models.briefs[0].instructions == "drop the sales centre map"


async def test_each_round_is_handed_over_as_it_ends():
    pdfs = store("SouthCal a")
    fix = RedactTerms(terms=["a"], why="leftover")
    models = FakeUnbrandModels(sorting("floor_plan"),
                               judge=lambda round_number, page: [leak(1)]
                               if round_number == 1 else [],
                               repair={1: [fix]})
    rounds: list[RoundResult] = []
    done = await run(pdfs, models, 1, on_round=rounds.append)
    assert [result.number for result in rounds] == [1, 2]
    assert rounds[0].judge == [leak(1)] and rounds[1].pdf == done.pdf
    assert set(rounds[0].seconds) == {"apply", "verify", "judge", "repair"}
    assert set(rounds[1].seconds) == {"apply", "verify", "judge"}


async def test_drop_actions_come_from_the_sort_with_its_reason():
    models = FakeUnbrandModels(sorting("marketing", "floor_plan", terms=()))
    done = await run(store("cover", "plan"), models, 2)
    assert done.actions[0] == DropPage(page=1, why="marketing: marketing")


async def test_judge_findings_come_back_in_page_order_whatever_finishes_first():
    class Slow(FakeUnbrandModels):
        async def judge(self, brief, page):
            await asyncio.sleep(0.02 if page.page == 1 else 0)
            return [leak(page.page)]

    models = Slow(sorting("floor_plan", "floor_plan", "floor_plan"))
    done = await run(store("a", "b", "c"), models, 3, max_repair_rounds=0)
    assert [finding.page for finding in done.judge] == [1, 2, 3]


async def test_a_pick_over_a_model_name_is_refused_and_the_name_stays():
    badge = DrawnElement(kind="shapes", bbox=(40, 90, 140, 120))
    pdfs = store("THE CARSON", elements={1: [badge]})
    pick = {1: [RemoveElement(page=1, element_id=1, why="looks like branding")]}
    models = FakeUnbrandModels(sorting("floor_plan", terms=()), pick=pick)
    done = await run(pdfs, models, 1)
    assert texts(pdfs, done.pdf) == ["THE CARSON"]
    assert "not the builder's" in done.outcomes[-1].detail


async def test_phones_and_emails_on_kept_pages_are_removed_even_if_the_sort_missed_them():
    pdfs = store("Call 905-682-9801 or sales@builder.ca", "cover 416-555-0100")
    models = FakeUnbrandModels(sorting("price_list", "marketing", terms=()))
    done = await run(pdfs, models, 2)
    assert texts(pdfs, done.pdf) == ["Call or"]
    terms = next(action for action in done.actions if isinstance(action, RedactTerms)).terms
    assert terms == ["905-682-9801", "sales@builder.ca"]  # not the dropped page's number


async def test_removing_a_sort_term_is_not_damage():
    """The sort is asked for the sales office address; its street number going
    is the point, not lost information."""
    pdfs = store("Sales office 3 Bright Side Dr Lot 12")
    models = FakeUnbrandModels(sorting("price_list", terms=["3 Bright Side Dr"]))
    done = await run(pdfs, models, 1)
    assert texts(pdfs, done.pdf) == ["Sales office Lot 12"]
    assert done.report.passed
    assert not [finding for finding in done.report.findings if finding.check is Check.DAMAGE]


async def test_contacts_go_from_a_page_the_guards_keep_whatever_the_sort_said():
    pdfs = store("From $899,990 call 905-682-9801", "plan")
    models = FakeUnbrandModels(sorting("marketing", "floor_plan", terms=()))
    done = await run(pdfs, models, 2)
    assert done.dropped_pages == []
    assert texts(pdfs, done.pdf) == ["From $899,990 call", "plan"]


async def test_a_sort_term_is_not_swept_for_in_the_output():
    """A short sort term ("ARISTA") matched OCR noise within one edit and failed a
    clean brochure; the text layer's matches are removed by redact_terms anyway."""
    class Noisy(FakePdfStore):
        def inspect(self, pdf, *, ocr):
            facts = super().inspect(pdf, ocr=ocr)
            for page in facts.pages:
                page.ocr = {mode: "earlrta lot" for mode in page.ocr}
            return facts

    pdfs = Noisy(SOURCE, [words("ARISTA Lot 12")])
    models = FakeUnbrandModels(sorting("floor_plan", terms=["ARISTA"]))
    done = await run(pdfs, models, 1)
    assert done.report.passed and models.repaired == []


async def test_a_page_whose_repair_proposes_nothing_is_not_asked_again():
    """Bright Side floor plans: pages 7 and 9 answered nothing in round 1, then the
    same refused removals in round 2, while another page kept the rounds going."""
    pdfs = store("Lot 12", "SouthCal a")
    models = FakeUnbrandModels(sorting("floor_plan", "floor_plan", terms=()),
                               judge=lambda round_number, page: [leak(page.page)],
                               repair={2: [RedactRect(page=2, box=(0, 0, 100, 100), why="logo")]})
    done = await run(pdfs, models, 2, max_repair_rounds=2)
    assert [page for page, _ in models.repaired] == [1, 2, 2]
    assert done.rounds == 3 and leak(1) in done.judge



async def test_a_picked_number_names_the_sources_element_when_an_edit_renumbers_the_page():
    """Bright Side floor plans p16: removing text rewrote the drawing, numbering
    the page again gave 15 elements for 13, and a picked number named another."""
    logo = DrawnElement(kind="shapes", bbox=(40, 300, 140, 330))
    photo = DrawnElement(kind="image", bbox=(10, 10, 60, 40))
    pdfs = store("SouthCal plan", elements={1: [logo]})
    open_source = pdfs.open

    def open_renumbering(pdf: bytes):
        session = open_source(pdf)
        redact_text = session.redact_text

        def renumbering(page, boxes):
            redact_text(page, boxes)
            session.element_map = {1: [photo, logo]}  # the photo now comes first
        session.redact_text = renumbering
        return session

    pdfs.open = open_renumbering
    models = FakeUnbrandModels(sorting("floor_plan"),
                               pick={1: [RemoveElement(page=1, element_id=1, why="logo")]})
    await run(pdfs, models, 1, max_repair_rounds=0)
    removed = [call for session in pdfs.sessions for call in session.calls
               if call[0] == "redact_area"]
    assert removed == [("redact_area", 1, (39, 299, 141, 331))]


async def test_steps_the_models_left_out_reach_the_approver_of_this_document_only():
    models = FakeUnbrandModels(sorting("floor_plan"))
    models.dropped.append("step from an earlier document")
    pick = models.pick

    async def pick_dropping_a_step(brief, page):
        models.dropped.append("step {'tool': 'remove_element'}: element_id missing")
        return await pick(brief, page)

    models.pick = pick_dropping_a_step
    done = await run(store("SouthCal a"), models, 1)
    assert done.dropped_steps == ["step {'tool': 'remove_element'}: element_id missing"]


async def test_a_negative_repair_round_limit_is_refused():
    with pytest.raises(ValueError, match="max_repair_rounds"):
        await run(store("SouthCal a"), FakeUnbrandModels(sorting("floor_plan")), 1,
                  max_repair_rounds=-1)


async def test_every_session_opened_is_closed():
    models = FakeUnbrandModels(sorting("floor_plan"), judge=lambda round_number, page: [leak(1)],
                               repair={1: [RedactRect(page=1, box=(0, 900, 100, 1000),
                                                      why="logo")]})
    pdfs = store("SouthCal a")
    await run(pdfs, models, 1, max_repair_rounds=1)
    assert pdfs.sessions and all(session.closed for session in pdfs.sessions)
