"""The LangChain adapter of UnbrandModels, on a scripted chat model. No network."""

import json
import ssl
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.capabilities.unbrander.adapters import models_langchain
from app.capabilities.unbrander.adapters.models_langchain import (
    CallLog,
    LangChainUnbrandModels,
    NoAnswer,
)
from app.capabilities.unbrander.domain import (
    Brief,
    Check,
    HitList,
    NumberedElement,
    PageSort,
    PageView,
    RedactRect,
    RemoveElement,
    Severity,
)

BRIEF = Brief(hits=HitList(builder="Arista Homes", project="SouthCal"), page_count=2)
PAGES = [PageView(page=page, jpeg=b"\xff\xd8" * 600,
                  text=f'<document_text page="{page}">x</document_text>',
                  elements=[NumberedElement(id=9, kind="image", box=(10, 10, 90, 60))])
         for page in (1, 3)]
PAGE = PAGES[1]
NO_STEP_FIELDS = {"element_id": None, "box_2d": None}
SORT = {"pages": [{"page": 1, "kind": "marketing", "keep": False, "why": "cover"},
                  {"page": 3, "kind": "floor_plan", "keep": True, "why": "plan"}],
        "terms": ["SouthCal"]}


class Scripted(GenericFakeChatModel):
    """Answers with the given messages, keeps what it was sent, and records how
    structured output was asked for."""

    seen: list
    asked: list
    failures: list

    def with_structured_output(self, schema, **kwargs):
        self.asked.append(kwargs)
        return self | RunnableLambda(lambda raw: {"raw": raw, "parsed": None,
                                                   "parsing_error": None})

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        if self.failures:
            raise self.failures.pop(0)
        return super()._generate(messages, *args, **kwargs)


def answer(body: dict | str, *, cost: float = 0.0) -> AIMessage:
    return AIMessage(content=body if isinstance(body, str) else json.dumps(body),
                     usage_metadata={"input_tokens": 100, "output_tokens": 20,
                                     "total_tokens": 120},
                     response_metadata={"cost": cost})


def step(**fields) -> dict:
    return {**NO_STEP_FIELDS, **fields}


def models(call_log=None, **scripts: list[AIMessage]):
    fakes = {role: Scripted(messages=iter(scripts.get(role, [])), seen=[], asked=[], failures=[])
             for role in ("sort", "pick", "judge", "repair")}
    return LangChainUnbrandModels(models=fakes, call_log=call_log), fakes


async def test_answers_are_asked_for_as_strict_json_schema():
    adapter, fakes = models(sort=[answer(SORT)])
    await adapter.sort(BRIEF, PAGES)
    assert fakes["sort"].asked == [{"method": "json_schema", "strict": True,
                                    "include_raw": True}]


async def test_sort_keeps_known_pages_once_and_the_terms():
    body = {**SORT, "pages": SORT["pages"] + [
        {"page": 3, "kind": "marketing", "keep": False, "why": "repeat"},
        {"page": 7, "kind": "marketing", "keep": False, "why": "made up"},
        {"page": 1, "kind": "poster", "keep": False, "why": "bad kind"}]}
    adapter, _ = models(sort=[answer(body)])
    sorting = await adapter.sort(BRIEF, PAGES)
    assert sorting.pages == [PageSort(page=1, kind="marketing", keep=False, why="cover"),
                             PageSort(page=3, kind="floor_plan", keep=True, why="plan")]
    assert sorting.terms == ["SouthCal"] and len(adapter.dropped) == 1


async def test_pick_becomes_actions_on_its_page_and_a_bad_step_is_dropped():
    adapter, _ = models(pick=[answer({"actions": [
        step(tool="remove_element", element_id=9, why="logo"),
        step(tool="redact_rect", box_2d=[900, 20, 960, 120], why="logo in a photo"),
        step(tool="redact_rect", box_2d=[0, 0], why="bad box"),
        {**step(tool="redact_terms", why="model name"), "terms": ["The Carson"]},
    ]})])
    actions = await adapter.pick(BRIEF, PAGE)
    assert actions == [
        RemoveElement(page=3, element_id=9, why="logo"),
        RedactRect(page=3, box=(20, 900, 120, 960), why="logo in a photo"),
    ]
    # Only the sort names text to remove (run 7: a repair took "The Carson").
    assert len(adapter.dropped) == 2 and "bad box" in adapter.dropped[0]


async def test_an_answer_without_the_list_is_asked_for_once_more():
    adapter, fakes = models(pick=[answer("I removed the logo."),
                                  answer({"actions": [step(tool="remove_element", element_id=9,
                                                           why="logo")]})])
    actions = await adapter.pick(BRIEF, PAGE)
    assert len(actions) == 1
    assert len(fakes["pick"].seen) == 2 and adapter.usage["pick"].calls == 2


async def test_a_sort_with_no_answer_twice_fails():
    adapter, _ = models(sort=[answer("no"), answer({"pages": "none", "terms": []})])
    with pytest.raises(NoAnswer, match="sort"):
        await adapter.sort(BRIEF, PAGES)


async def test_a_judge_with_no_answer_twice_blocks_that_page_for_a_person():
    adapter, _ = models(judge=[answer(""), answer("{}")])
    found = await adapter.judge(BRIEF, PAGE)
    assert [(finding.check, finding.severity, finding.page) for finding in found] == [
        (Check.VISUAL, Severity.BLOCK, 3)]


async def test_a_pick_or_repair_with_no_answer_twice_adds_nothing():
    adapter, _ = models(pick=[answer(""), answer("")], repair=[answer(""), answer("")])
    assert await adapter.pick(BRIEF, PAGE) == []
    assert await adapter.repair(BRIEF, PAGE, ["visible: logo"]) == []
    assert adapter.dropped == ["pick of page 3: no answer", "repair of page 3: no answer"]


async def test_a_leak_with_a_malformed_element_is_kept_without_it():
    """Flash once wrote a box as a string; that must not lose the whole judgement."""
    adapter, _ = models(judge=[answer({"leaks": [
        {"element_id": "9]", "what": "monogram"},
        {"element_id": 4, "what": "logo"},
    ]})])
    found = await adapter.judge(BRIEF, PAGE)
    assert [(finding.page, finding.detail) for finding in found] == [
        (3, "monogram"), (3, "logo (element 4)")]


async def test_pages_go_to_the_model_as_text_and_images_in_the_user_message():
    adapter, fakes = models(pick=[answer({"actions": []})])
    await adapter.pick(BRIEF, PAGE)
    system, user = fakes["pick"].seen[0]
    assert "SouthCal" in system.content
    assert [block["type"] for block in user.content] == ["text", "image"]
    # The element's box is x first in the domain, (10, 10, 90, 60); the model is
    # shown it in the box_2d order it answers in.
    assert "Page 3. Elements: 9 image box_2d [10, 10, 60, 90]" in user.content[0]["text"]


async def test_the_sort_sees_pages_without_the_element_list():
    adapter, fakes = models(sort=[answer(SORT)])
    await adapter.sort(BRIEF, PAGES)
    user = fakes["sort"].seen[0][1]
    assert [block["type"] for block in user.content] == ["text", "image", "text", "image"]
    assert "Elements" not in user.content[2]["text"]


async def test_usage_is_summed_per_role():
    adapter, _ = models(sort=[answer(SORT, cost=0.01)],
                        repair=[answer({"actions": []}, cost=0.002)] * 2)
    await adapter.sort(BRIEF, PAGES)
    await adapter.repair(BRIEF, PAGE, ["visible: logo"])
    await adapter.repair(BRIEF, PAGE, ["visible: logo"])
    assert (adapter.usage["sort"].calls, adapter.usage["sort"].cost) == (1, 0.01)
    assert (adapter.usage["repair"].calls, adapter.usage["repair"].input_tokens) == (2, 200)
    assert adapter.usage["judge"].calls == 0


async def test_operator_instructions_are_delimited():
    adapter, fakes = models(sort=[answer(SORT)])
    await adapter.sort(BRIEF.model_copy(update={"instructions": "keep page 4"}), PAGES)
    system = fakes["sort"].seen[0][0].content
    assert "<operator_instructions>\nkeep page 4\n</operator_instructions>" in system


async def test_the_call_log_keeps_every_call_without_the_images(tmp_path):
    path = tmp_path / "calls.jsonl"
    adapter, _ = models(call_log=path, judge=[answer("not json"), answer({"leaks": []})])
    await adapter.judge(BRIEF, PAGE)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(line["role"], line["attempt"]) for line in lines] == [("judge", 1), ("judge", 2)]
    assert lines[0]["answer"] == "not json" and lines[1]["usage"]["input_tokens"] == 100
    user = lines[0]["prompt"][1]
    assert user[1].startswith("[image") and "Page 3." in user[0]
    assert "base64" not in path.read_text()


async def test_the_call_log_records_an_error(tmp_path):
    path = tmp_path / "calls.jsonl"
    log = CallLog(path)
    run_id = uuid4()
    await log.on_chat_model_start({}, [[]], run_id=run_id, metadata={"role": "sort",
                                                                      "attempt": 1})
    await log.on_llm_error(TimeoutError("read timed out"), run_id=run_id)
    line = json.loads(path.read_text())
    assert (line["role"], line["error"]) == ("sort", "TimeoutError: read timed out")


def test_each_role_has_an_output_cap():
    adapter = LangChainUnbrandModels(api_key="test-key-not-real", sort_model="google/a",
                                     pick_model="google/b", judge_model="google/c",
                                     repair_model="google/d")
    caps = {role: model.max_tokens for role, model in adapter._models.items()}
    assert caps == {"sort": 8_000, "pick": 2_000, "judge": 2_000, "repair": 2_000}


async def test_a_leak_repeated_on_the_page_counts_once():
    """Run 5: Flash wrote one leak thousands of times."""
    same = {"element_id": 4, "what": "Arista Homes"}
    adapter, _ = models(judge=[answer({"leaks": [same, same, same]})])
    assert len(await adapter.judge(BRIEF, PAGE)) == 1


async def test_a_broken_connection_is_tried_again(monkeypatch):
    monkeypatch.setattr(models_langchain, "TRANSPORT_WAITS", (0, 0))
    adapter, fakes = models(pick=[answer({"actions": []})])
    fakes["pick"].failures.append(ssl.SSLError("bad record mac"))
    assert await adapter.pick(BRIEF, PAGE) == []
    assert len(fakes["pick"].seen) == 2


async def test_a_connection_broken_three_times_raises(monkeypatch):
    monkeypatch.setattr(models_langchain, "TRANSPORT_WAITS", (0, 0))
    adapter, fakes = models(sort=[answer(SORT)])
    fakes["sort"].failures.extend(ssl.SSLError("bad record mac") for _ in range(3))
    with pytest.raises(ssl.SSLError):
        await adapter.sort(BRIEF, PAGES)


async def test_any_other_error_is_not_tried_again(monkeypatch):
    monkeypatch.setattr(models_langchain, "TRANSPORT_WAITS", (0, 0))
    adapter, fakes = models(sort=[answer(SORT)])
    fakes["sort"].failures.append(ValueError("401 invalid key"))
    with pytest.raises(ValueError, match="401"):
        await adapter.sort(BRIEF, PAGES)
    assert len(fakes["sort"].seen) == 1


def test_thinking_is_set_per_role_and_raises_that_roles_cap():
    adapter = LangChainUnbrandModels(api_key="test-key-not-real", sort_model="google/a",
                                     pick_model="google/b", judge_model="google/c",
                                     repair_model="google/d",
                                     thinking={"pick": "off", "judge": "low"})
    settings = {role: (model.max_tokens, model.reasoning)
                for role, model in adapter._models.items()}
    assert settings == {"sort": (8_000, None), "pick": (2_000, {"enabled": False}),
                        "judge": (10_000, {"effort": "low"}), "repair": (2_000, None)}


async def test_two_elements_with_the_same_description_are_two_leaks():
    adapter, _ = models(judge=[answer({"leaks": [{"element_id": 3, "what": "ARISTA logo"},
                                                 {"element_id": 7, "what": "ARISTA logo"}]})])
    found = await adapter.judge(BRIEF, PAGE)
    assert [finding.detail for finding in found] == [
        "ARISTA logo (element 3)", "ARISTA logo (element 7)"]
