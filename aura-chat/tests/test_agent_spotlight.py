"""Which projects become cards under an inventory answer.

The bug this pins: `inventory_summary` used to card the cheapest and dearest
projects on every call, so "how many projects do we have?" answered "158 across
36 cities" and then showed two project cards underneath. A realtor reads a card
as a result. Two of them under an answer that was not about them is not clutter,
it is a contradiction -- and on "the least expensive in Brampton" one of the two
was the *most* expensive project in the city.
"""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from tests.test_agent import a_project, drain, runtime, scripted, viewed

CHEAP = a_project(id="AK-CHEAP", name="Cheap", starting_price=370_990)
DEAR = a_project(id="AK-DEAR", name="Dear", starting_price=1_469_900)


async def _cards(args: dict) -> list[str]:
    model = scripted(
        ModelResponse(parts=[ToolCallPart("inventory_summary", args)]),
        ModelResponse(parts=[TextPart("Here you go.")]),
    )
    events = await drain(runtime(model), viewed([CHEAP, DEAR]))
    projects = next(e for e in events if e["type"] == "projects")["projects"]
    return [p["name"] for p in projects]


async def test_a_count_question_produces_no_cards():
    """The regression. This is what "how many projects do we have?" hits."""
    assert await _cards({}) == []


async def test_spotlight_cheapest_shows_only_the_cheapest():
    assert await _cards({"spotlight": "cheapest"}) == ["Cheap"]


async def test_spotlight_dearest_shows_only_the_dearest():
    assert await _cards({"spotlight": "dearest"}) == ["Dear"]


async def test_spotlight_both_shows_both():
    assert sorted(await _cards({"spotlight": "both"})) == ["Cheap", "Dear"]


async def test_an_unknown_spotlight_shows_nothing_rather_than_everything():
    """A model that invents a value must fail toward silence. Showing every
    project on an unrecognised string is how a typo becomes the old bug back."""
    assert await _cards({"spotlight": "lowest"}) == []


async def test_the_model_still_receives_both_records_whatever_is_carded():
    """Only the card is conditional. If the data went away with it, the model
    could no longer answer "what is the cheapest" at all."""
    seen: list[str] = []

    async def capture(messages, info):
        seen.append(str(messages))
        from pydantic_ai.models.function import DeltaToolCall

        if len(seen) == 1:
            yield {0: DeltaToolCall(name="inventory_summary", json_args="{}")}
        else:
            yield "ok"

    from pydantic_ai.models.function import FunctionModel

    from app.adapters.agent_pydantic import PydanticAgentRuntime

    rt = PydanticAgentRuntime(
        api_key="", model_name="test", model=FunctionModel(stream_function=capture)
    )
    await drain(rt, viewed([CHEAP, DEAR]))
    transcript = " ".join(seen)
    assert "370990" in transcript and "1469900" in transcript
