"""UnbrandModels over LangChain and OpenRouter: one structured call per method.

Answers use strict JSON schema output: the provider constrains generation to
the schema, so the model cannot answer in prose or put a string where a list
goes. Function calling only asked it to, and Gemini Flash did both in real runs.

The schema the model fills is flat (one nullable field per tool argument)
rather than the domain's tagged union: a discriminated union becomes `oneOf`,
which not every provider behind OpenRouter accepts. Each step is converted to a
domain Action here; one that does not fit is dropped and listed in `dropped`,
so a single bad step never costs the whole answer.

Page images travel in the user message. OpenRouter accepts only text in tool
messages, and there is no tool loop here anyway.
"""

import asyncio
import base64
import json
import ssl
import time
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ..domain import (
    Action,
    Brief,
    Check,
    Finding,
    PageKind,
    PageSort,
    PageView,
    Severity,
    Sorting,
    Usage,
    from_box_2d,
    to_box_2d,
)
from ..prompts import judge_prompt, pick_prompt, repair_prompt, sort_prompt

ROLES = ("sort", "pick", "judge", "repair")
# A sort call carries every page as an image and the SDK's default read timeout
# cut the first real run short. Ten minutes matches the per-document budget.
TIMEOUT_MS = 600_000
ATTEMPTS = 2
# A sort answer is a line per page plus a list of names; per-page answers are a
# few actions. Without a cap, Flash once repeated one leak until its 65k limit
# (269 s, $0.17). A capped loop fails to parse and is asked again at once.
MAX_OUTPUT_TOKENS = {"sort": 8_000, "pick": 2_000, "judge": 2_000, "repair": 2_000}
# Thinking tokens count against the output cap; a role that thinks gets this much more.
THINKING_ALLOWANCE = 8_000
# The OpenRouter SDK retries only httpx network errors and timeouts; an
# ssl.SSLError that httpcore did not wrap (BAD_RECORD_MAC on a stale pooled
# connection, run 5) reached us as permanent and ended the run.
TRANSPORT_ERRORS = (ssl.SSLError, httpx.TransportError, ConnectionError)
TRANSPORT_WAITS = (2, 5)  # seconds before the second and third try
_action = TypeAdapter(Action)


class NoAnswer(ValueError):
    """The model returned nothing that parses as the schema, on every attempt."""


class PageSortItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int
    kind: PageKind
    keep: bool
    why: str


class SortAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pages: list[PageSortItem]
    terms: list[str]


class Step(BaseModel):
    """One action on one page. Fields the tool does not take are null. No
    redact_terms here: only the sort, which reads the whole document, names text
    to remove. A repair that saw one page took "The Carson", a model name (run 7)."""

    model_config = ConfigDict(extra="forbid")
    tool: Literal["remove_element", "redact_rect"]
    why: str
    element_id: int | None
    # [ymin, xmin, ymax, xmax] on the page's 0-1000 grid: Gemini's native order.
    # Flash answered in it whatever order was asked, and asking for x first makes
    # its boxes much worse (simedw.com, 2025). Turned into x first in _actions.
    box_2d: list[int] | None


class Steps(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[Step]


class Leak(BaseModel):
    model_config = ConfigDict(extra="forbid")
    element_id: int | None
    what: str


class Leaks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leaks: list[Leak]


class CallLog(AsyncCallbackHandler):
    """Appends one JSON line per model call to `path`, as each call ends, so a
    run that dies later keeps the evidence of every call before it. Images are
    replaced by their size; the text sent and the raw answer are kept whole."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._open: dict[UUID, dict[str, Any]] = {}

    async def on_chat_model_start(self, serialized: dict[str, Any],
                                  messages: list[list[BaseMessage]], *, run_id: UUID,
                                  metadata: dict[str, Any] | None = None,
                                  **kwargs: Any) -> None:
        metadata = metadata or {}
        self._open[run_id] = {
            "role": metadata.get("role"), "attempt": metadata.get("attempt"),
            "model": metadata.get("ls_model_name"),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "clock": time.monotonic(),
            "prompt": [_loggable(message) for message in messages[0]],
        }

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        message = response.generations[0][0].message
        self._write(run_id, {
            "answer": message.content,
            "usage": getattr(message, "usage_metadata", None),
            "cost": message.response_metadata.get("cost"),
        })

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._write(run_id, {"error": f"{type(error).__name__}: {error}"})

    def _write(self, run_id: UUID, result: dict[str, Any]) -> None:
        entry = self._open.pop(run_id, {})
        entry["seconds"] = round(time.monotonic() - entry.pop("clock", time.monotonic()), 2)
        with self._path.open("a") as log:
            log.write(json.dumps({**entry, **result}, default=str) + "\n")


class LangChainUnbrandModels:
    def __init__(self, *, api_key: str = "", sort_model: str = "", pick_model: str = "",
                 judge_model: str = "", repair_model: str = "",
                 thinking: dict[str, str] | None = None,
                 models: dict[str, BaseChatModel] | None = None,
                 call_log: Path | None = None) -> None:
        """`thinking` maps a role to an OpenRouter reasoning effort ("low",
        "medium", "high") or "off"; a role not named keeps the model's default.
        Thinking helped some models' visual answers and hurt Gemini 2.5 Flash's
        boxes, so it is chosen per role by the model check."""
        if models is None:
            from langchain_openrouter import ChatOpenRouter

            names = {"sort": sort_model, "pick": pick_model, "judge": judge_model,
                     "repair": repair_model}
            models = {role: ChatOpenRouter(model=names[role], api_key=api_key, temperature=0,
                                           timeout=TIMEOUT_MS,
                                           **_thinking((thinking or {}).get(role), role))
                      for role in ROLES}
        self._models = models
        self._callbacks = [CallLog(call_log)] if call_log else []
        self.usage: dict[str, Usage] = {role: Usage() for role in ROLES}
        self.dropped: list[str] = []

    async def sort(self, brief: Brief, pages: list[PageView]) -> Sorting:
        # No answer here leaves nothing to apply, so NoAnswer fails the job.
        answer = await self._call("sort", SortAnswer, "pages", sort_prompt(brief),
                                  _page_blocks(pages, with_elements=False))
        known = {view.page for view in pages}
        out: dict[int, PageSort] = {}
        for item in answer["pages"]:
            try:
                page = PageSort.model_validate(item)
            except ValidationError as error:
                self.dropped.append(f"page {item!r:.200}: {error.errors()[0]['msg']}")
                continue
            if page.page in known:
                out.setdefault(page.page, page)
        terms = answer.get("terms")
        terms = [term for term in terms if isinstance(term, str)] if isinstance(terms, list) else []
        return Sorting(pages=sorted(out.values(), key=lambda page: page.page), terms=terms)

    async def pick(self, brief: Brief, page: PageView) -> list[Action]:
        try:
            answer = await self._call("pick", Steps, "actions", pick_prompt(brief),
                                      _page_blocks([page]))
        except NoAnswer:
            # The judge sees the page next and a repair can still act on it.
            self.dropped.append(f"pick of page {page.page}: no answer")
            return []
        return self._actions(page.page, answer["actions"])

    async def judge(self, brief: Brief, page: PageView) -> list[Finding]:
        try:
            answer = await self._call("judge", Leaks, "leaks", judge_prompt(brief),
                                      _page_blocks([page], with_text=False))
        except NoAnswer:
            # The output still exists and verify() has run on it; a person
            # looks at the page the judge could not.
            return [Finding(check=Check.VISUAL, severity=Severity.BLOCK, page=page.page,
                            detail="the visual check gave no answer; look at this page")]
        # Two elements may share a description ("ARISTA logo" on elements 3 and
        # 7); each is its own leak for the repair.
        seen: set[tuple[int | None, str]] = set()
        out = []
        for item in answer["leaks"]:
            leak = self._leak(item)
            if leak and (leak.element_id, leak.what) not in seen:
                seen.add((leak.element_id, leak.what))
                where = f" (element {leak.element_id})" if leak.element_id is not None else ""
                out.append(Finding(check=Check.VISUAL, severity=Severity.RETRY, page=page.page,
                                   detail=leak.what + where))
        return out

    async def repair(self, brief: Brief, page: PageView, problems: list[str]) -> list[Action]:
        try:
            answer = await self._call("repair", Steps, "actions", repair_prompt(brief, problems),
                                      _page_blocks([page]))
        except NoAnswer:
            # The problems stay in the report for the approver.
            self.dropped.append(f"repair of page {page.page}: no answer")
            return []
        return self._actions(page.page, answer["actions"])

    async def _call(self, role: str, schema: type[BaseModel], key: str, prompt: str,
                    blocks: list[dict[str, Any]]) -> dict[str, Any]:
        """The answer as parsed JSON, unvalidated, so one malformed item is
        dropped on its own rather than costing the whole answer. An answer
        without a list under `key` is asked for once more."""
        runnable = self._models[role].with_structured_output(
            schema, method="json_schema", strict=True, include_raw=True)
        messages = [SystemMessage(prompt), HumanMessage(content=blocks)]
        problem = ""
        for attempt in range(1, ATTEMPTS + 1):
            result = await self._invoke(runnable, messages, role, attempt)
            raw: AIMessage = result["raw"]
            self._count(role, raw)
            try:
                answer = json.loads(raw.text)
                items = answer[key]
            except (ValueError, KeyError, TypeError) as error:
                problem = f"{type(error).__name__}: {error}"
                continue
            if isinstance(items, list):
                return answer
            problem = f"{key} is not a list: {items!r:.200}"
        raise NoAnswer(f"{role}: no usable {schema.__name__} after {ATTEMPTS} attempts "
                       f"({problem})")

    async def _invoke(self, runnable: Any, messages: list[BaseMessage], role: str,
                      attempt: int) -> dict[str, Any]:
        """One answer, retrying only a broken connection. Not the same as asking
        again: a model that answered badly is re-asked in `_call`."""
        config = {"callbacks": self._callbacks, "metadata": {"role": role, "attempt": attempt}}
        for wait in TRANSPORT_WAITS:
            try:
                return await runnable.ainvoke(messages, config=config)
            except TRANSPORT_ERRORS:
                await asyncio.sleep(wait)
        return await runnable.ainvoke(messages, config=config)

    def _count(self, role: str, raw: AIMessage) -> None:
        usage = self.usage[role]
        usage.calls += 1
        token_usage = raw.usage_metadata or {}
        usage.input_tokens += token_usage.get("input_tokens", 0)
        usage.output_tokens += token_usage.get("output_tokens", 0)
        usage.cost += float(raw.response_metadata.get("cost") or 0)

    def _actions(self, page: int, items: list[Any]) -> list[Action]:
        """Steps for one page as domain actions; the page comes from the call,
        not the model."""
        out = []
        for item in items:
            try:
                step = Step.model_validate(item)
                fields: dict[str, Any] = {"tool": step.tool, "why": step.why}
                if step.tool == "remove_element":
                    fields |= {"page": page, "element_id": step.element_id}
                else:
                    box = step.box_2d or []
                    fields |= {"page": page,
                               "box": from_box_2d(box) if len(box) == 4 else box}
                out.append(_action.validate_python(fields))
            except ValidationError as error:
                self.dropped.append(f"step {item!r:.200}: {error.errors()[0]['msg']}")
        return out

    def _leak(self, item: Any) -> Leak | None:
        """A leak with a malformed element number still says the page has
        branding, so it is kept without the number rather than lost."""
        try:
            return Leak.model_validate(item)
        except ValidationError as error:
            if isinstance(item, dict) and "element_id" in item:
                try:
                    return Leak.model_validate({**item, "element_id": None})
                except ValidationError:
                    pass
            self.dropped.append(f"leak {item!r:.200}: {error.errors()[0]['msg']}")
            return None


def _thinking(effort: str | None, role: str) -> dict[str, Any]:
    cap = MAX_OUTPUT_TOKENS[role]
    if effort is None:
        return {"max_tokens": cap}
    if effort == "off":
        return {"max_tokens": cap, "reasoning": {"enabled": False}}
    return {"max_tokens": cap + THINKING_ALLOWANCE, "reasoning": {"effort": effort}}


def _page_blocks(pages: list[PageView], *, with_text: bool = True,
                 with_elements: bool = True) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for view in pages:
        head = f"Page {view.page}."
        if with_elements:
            # In box_2d order, the order the model answers in: a list shown x
            # first beside a prompt asking for y first invites copied numbers.
            listed = "; ".join(f"{element.id} {element.kind} box_2d {to_box_2d(element.box)}"
                               for element in view.elements)
            head += f" Elements: {listed or 'none'}."
        blocks.append({"type": "text", "text": f"{head}\n{view.text}" if with_text else head})
        blocks.append({"type": "image", "base64": base64.b64encode(view.jpeg).decode(),
                       "mime_type": "image/jpeg"})
    return blocks


def _loggable(message: BaseMessage) -> str | list[str]:
    """The message as text. Any non-text block (an image, in whichever shape
    LangChain has converted it to by now) is replaced by its type and size."""
    if isinstance(message.content, str):
        return message.content
    out = []
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "text":
            out.append(block.get("text", ""))
        elif isinstance(block, dict):
            out.append(f"[{block.get('type')} {len(json.dumps(block)) // 1024} KB]")
        else:
            out.append(str(block))
    return out
