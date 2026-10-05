"""The agent loop, driven by a scripted model.

FunctionModel lets us decide exactly what the model "asks for", so these test
our wiring -- that a tool call reaches the right repo, that results come back as
cards, that a failure degrades honestly -- rather than testing whether an LLM
behaves. No network, no bill.
"""

import json

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.adapters.agent_pydantic import MAX_STEPS, PydanticAgentRuntime, _for_model
from app.adapters.projects_redacting import RedactingProjectRepo
from app.domain import ChatMode, Claims, Project, Role, Viewer
from tests.fakes import FakeProjectRepo

AUTH = "tok"
CLAIMS = Claims(user="sarath", role=Role.REALTOR, issued_ms=0)


def a_project(**over) -> Project:
    base = dict(
        id="AK-0001", name="Reva", city="BRAMPTON", builder="Great Gulf",
        property_type="Townhome", categories=["townhome"], starting_price=899_900,
        commission="4%", builder_login="agent@builder",
    )
    base.update(over)
    return Project(**base)


def scripted(*turns):
    """A model that plays back a fixed sequence of turns.

    run_stream drives a model through its streaming interface, so a turn is
    emitted either as tool-call deltas or as text chunks. Running past the end
    of the script repeats the last turn rather than raising: an off-by-one in a
    fixture should surface as a failed assertion about behaviour, not as a
    StopIteration from somewhere inside the framework.
    """
    state = {"i": 0}

    def _next() -> ModelResponse:
        i = min(state["i"], len(turns) - 1)
        state["i"] += 1
        return turns[i]

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        turn = _next()
        for part in turn.parts:
            if isinstance(part, ToolCallPart):
                yield {
                    0: DeltaToolCall(
                        name=part.tool_name, json_args=json.dumps(part.args or {})
                    )
                }
            elif isinstance(part, TextPart):
                # In chunks, so the streaming path is genuinely exercised.
                for word in part.content.split(" "):
                    yield word + " "

    return FunctionModel(stream_function=stream)


def runtime(model) -> PydanticAgentRuntime:
    return PydanticAgentRuntime(api_key="", model_name="test", model=model)


def viewed(projects, mode=ChatMode.REALTOR):
    return RedactingProjectRepo(FakeProjectRepo(projects), Viewer(role=Role.REALTOR, mode=mode))


async def drain(rt, repo, question="show me projects", mode=ChatMode.REALTOR):
    return [e async for e in rt.stream(
        question=question, claims=CLAIMS, auth=AUTH, mode=mode, repo=repo
    )]


async def test_a_tool_call_reaches_the_repo_and_comes_back_as_cards():
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {"city": "BRAMPTON"})]),
        ModelResponse(parts=[TextPart("Two townhomes in Brampton.")]),
    )
    events = await drain(runtime(model), viewed([a_project()]))
    kinds = [e["type"] for e in events]
    assert "text" in kinds and kinds[-1] == "done"
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert [c["name"] for c in cards] == ["Reva"]


async def test_cards_come_from_tool_results_not_from_the_prose():
    """The model saying "$1.2M" must not change what the card shows -- that is
    how a number drifts between the sheet and the buyer."""
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {})]),
        ModelResponse(parts=[TextPart("Reva starts around $1.2M.")]),
    )
    events = await drain(runtime(model), viewed([a_project(starting_price=899_900)]))
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert cards[0]["starting_price"] == 899_900


async def test_client_mode_records_never_reach_the_model():
    """The redaction happens before the tool returns, so there is no point at
    which a confidential value is in the prompt."""
    seen: list[str] = []

    async def stream(messages, info):
        seen.append(str(messages))
        if len(seen) == 1:
            yield {0: DeltaToolCall(name="search_projects", json_args="{}")}
        else:
            yield "ok"

    events = await drain(
        runtime(FunctionModel(stream_function=stream)),
        viewed([a_project()], ChatMode.CLIENT),
        mode=ChatMode.CLIENT,
    )
    transcript = " ".join(seen)
    assert "4%" not in transcript and "agent@builder" not in transcript
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert cards and "commission" not in cards[0]


async def test_a_model_failure_becomes_a_recoverable_message():
    """AUR-45: a stack trace is not an answer, and neither is half a sentence
    that reads like a whole one."""
    async def boom(messages, info):
        raise RuntimeError("model unreachable")
        yield ""  # pragma: no cover -- makes this an async generator

    events = await drain(runtime(FunctionModel(stream_function=boom)), viewed([a_project()]))
    assert events[-1]["type"] == "error"
    assert "model unreachable" in events[-1]["detail"]
    assert not any(e["type"] == "done" for e in events)


async def test_an_empty_search_is_reported_not_padded():
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {"city": "NOWHERE"})]),
        ModelResponse(parts=[TextPart("Nothing matched that.")]),
    )
    events = await drain(runtime(model), viewed([a_project()]))
    assert next(e for e in events if e["type"] == "projects")["projects"] == []


async def test_the_same_project_is_not_carded_twice():
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {"city": "BRAMPTON"})]),
        ModelResponse(parts=[ToolCallPart("get_project", {"project_id": "AK-0001"})]),
        ModelResponse(parts=[TextPart("Here it is.")]),
    )
    events = await drain(runtime(model), viewed([a_project()]))
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert len(cards) == 1


def test_empty_fields_are_omitted_rather_than_sent_as_blanks():
    """A page of empty strings teaches a model that missing data is normal and
    invites it to fill the gaps."""
    out = _for_model(a_project(occupancy="", incentives="", bedrooms=""))
    assert "occupancy" not in out and "incentives" not in out
    assert out["name"] == "Reva"


async def test_a_model_that_never_stops_calling_tools_is_cut_off():
    """The previous version of this test asserted MAX_STEPS <= 10, which passed
    while the constant was wired to nothing. Drive a model that loops forever
    and prove the run actually ends."""
    calls = {"n": 0}

    async def forever(messages, info):
        calls["n"] += 1
        yield {0: DeltaToolCall(name="search_projects", json_args="{}")}

    events = await drain(runtime(FunctionModel(stream_function=forever)), viewed([a_project()]))
    assert events[-1]["type"] == "error"
    # Bounded by our own limit, not by the framework's default of 50.
    assert calls["n"] <= MAX_STEPS + 1


async def test_the_model_and_agent_are_built_once_not_per_request():
    """A provider owns an AsyncOpenAI client and its connection pool, and
    nothing here closes one: building them per message leaks a pool per
    question until the process runs out of sockets."""
    rt = PydanticAgentRuntime(api_key="k", model_name="openai/gpt-4o-mini")
    first, second = rt._model_for(), rt._model_for()
    assert first is second

    model = scripted(ModelResponse(parts=[TextPart("hi")]))
    rt2 = runtime(model)
    await drain(rt2, viewed([a_project()]))
    await drain(rt2, viewed([a_project()]))
    assert len(rt2._agents) == 1


async def test_a_failure_while_building_the_cards_still_reports_an_error(monkeypatch):
    """Text streams, then serialisation fails. Ending the stream silently would
    leave a conforming client waiting under a finished answer."""
    import app.adapters.agent_pydantic as mod

    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {})]),
        ModelResponse(parts=[TextPart("here you go")]),
    )
    # _for_client is only ever used for the card pass, so failing it leaves the
    # tool's own return -- which goes through _for_model -- working.
    def explode(p):
        raise TypeError("not serialisable")

    monkeypatch.setattr(mod, "_for_client", explode)
    events = await drain(runtime(model), viewed([a_project()]))
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "done" for e in events)


async def test_one_card_per_id_even_when_a_single_result_set_repeats_one():
    """Two rows can share a PROJECT ID while the column is entered by hand."""
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {})]),
        ModelResponse(parts=[TextPart("ok")]),
    )
    twins = [a_project(name="First"), a_project(name="Second")]   # same id
    events = await drain(runtime(model), viewed(twins))
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert len(cards) == 1


async def test_healthy_does_not_spend_money():
    """A completion would be the stronger check and would bill on every uptime
    probe."""
    assert await runtime(scripted()).healthy() is True
    assert await PydanticAgentRuntime(api_key="", model_name="x").healthy() is False


async def test_a_named_project_is_found_without_an_id():
    """A realtor naming a project is not handing over an id. Refusing that made
    Aura deny that projects in its own sheet existed."""
    model = scripted(
        ModelResponse(parts=[ToolCallPart("get_project", {"project_id_or_name": "Reva"})]),
        ModelResponse(parts=[TextPart("Found it.")]),
    )
    events = await drain(runtime(model), viewed([a_project(name="Reva")]))
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert [c["name"] for c in cards] == ["Reva"]


async def test_an_ambiguous_name_returns_candidates_not_a_denial():
    """Two Brampton projects really are both called Mayfield Village. The
    realtor needs to be asked which, not told neither exists."""
    from app.adapters.agent_pydantic import build_agent

    twins = [
        a_project(id="AK-1", name="Mayfield Village", builder="Royal Pine"),
        a_project(id="AK-2", name="Mayfield Village", builder="Regal Crest"),
    ]
    model = scripted(
        ModelResponse(parts=[ToolCallPart("get_project", {"project_id_or_name": "Mayfield Village"})]),
        ModelResponse(parts=[TextPart("Which one?")]),
    )
    events = await drain(runtime(model), viewed(twins), question="tell me about Mayfield Village")
    cards = next(e for e in events if e["type"] == "projects")["projects"]
    assert {c["builder"] for c in cards} == {"Royal Pine", "Regal Crest"}


async def test_tool_events_arrive_before_the_text_not_after():
    """stream_text yields nothing until the tools are done. Holding the tool
    event until then means "searching Brampton..." lands after the search --
    exactly the seconds it exists to fill."""
    import asyncio

    released = asyncio.Event()

    class SlowRepo(FakeProjectRepo):
        async def search(self, filters, *, auth):
            await released.wait()          # the tool hangs until we let it go
            return await super().search(filters, auth=auth)

    repo = RedactingProjectRepo(
        SlowRepo([a_project()]), Viewer(role=Role.REALTOR, mode=ChatMode.REALTOR)
    )
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {})]),
        ModelResponse(parts=[TextPart("done")]),
    )
    stream = runtime(model).stream(
        question="q", claims=CLAIMS, auth=AUTH, mode=ChatMode.REALTOR, repo=repo
    )
    # The tool event must be available while the tool is still running.
    first = await asyncio.wait_for(stream.__anext__(), timeout=2)
    assert first["type"] == "tool"
    released.set()
    rest = [e async for e in stream]
    assert [e["type"] for e in rest][-1] == "done"


async def test_a_client_that_stops_listening_does_not_leave_the_run_going():
    """Closing the tab mid-answer would otherwise keep the model running, and
    billing, with nobody reading it."""
    model = scripted(
        ModelResponse(parts=[ToolCallPart("search_projects", {})]),
        ModelResponse(parts=[TextPart("a b c d e")]),
    )
    stream = runtime(model).stream(
        question="q", claims=CLAIMS, auth=AUTH, mode=ChatMode.REALTOR,
        repo=viewed([a_project()]),
    )
    await stream.__anext__()
    await stream.aclose()          # must not hang or raise
