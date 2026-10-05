"""Stored rows -> the turns the model sees.

Pure and database-free, which is the point: this is the compare-by-name fix and
it can be proven before anything writes a row.
"""

from app.domain import MAX_HISTORY_TURNS, Turn, source_line, turns_from

ANSWER = {
    "role": "assistant",
    "message": "Two match: Ivy Rogue and New Kleinburg.",
    "sources": [{"id": "AK-0021", "name": "Ivy Rogue"}, {"id": "AK-0022", "name": "New Kleinburg"}],
}


def test_an_answer_carries_the_ids_it_was_built_from():
    """known-issues 4. Without this the model has names and no ids, so asked to
    "compare the first two" it invents oakville-townhomes-1."""
    out = turns_from([{"role": "user", "message": "townhomes in Oakville?"}, ANSWER])
    assert "AK-0021" in out[-1].content and "AK-0022" in out[-1].content
    assert "Ivy Rogue" in out[-1].content   # the model matches on what it wrote


def test_the_answer_text_survives_alongside_the_ids():
    assert out_text().startswith("Two match: Ivy Rogue and New Kleinburg.")


def out_text() -> str:
    return turns_from([ANSWER])[0].content


def test_a_question_is_left_exactly_as_asked():
    """Only assistant turns get a source line. A question with an id list
    appended reads as though the realtor typed it."""
    out = turns_from([{"role": "user", "message": "townhomes in Oakville?", "sources": [{"id": "X"}]}])
    assert out[0].content == "townhomes in Oakville?"


def test_an_answer_with_no_sources_is_unchanged():
    out = turns_from([{"role": "assistant", "message": "I could not confirm that."}])
    assert out[0].content == "I could not confirm that."
    assert "[projects:" not in out[0].content


def test_a_project_with_no_id_is_skipped_not_named():
    """Project.id is None until PROJECT ID is filled in. Naming one without an
    id would hand the model a reference it cannot look up -- the exact failure
    this function exists to prevent."""
    line = source_line([{"id": "", "name": "Nameless"}, {"id": "AK-1", "name": "Real"}])
    assert "Nameless" not in line
    assert "AK-1 Real" in line


def test_sources_are_capped():
    """Deps.collected accumulates across every tool call in a run, so a
    six-search answer can carry far more projects than it named."""
    line = source_line([{"id": f"AK-{i}", "name": f"P{i}"} for i in range(40)])
    assert line.count(";") == 11          # 12 entries, 11 separators


def test_only_the_last_turns_travel():
    """A long conversation keeps its recent context and drops its opening --
    the half a realtor is actively refining."""
    rows = [{"role": "user", "message": f"q{i}"} for i in range(60)]
    out = turns_from(rows)
    assert len(out) == MAX_HISTORY_TURNS
    assert out[-1].content == "q59"
    assert out[0].content == "q40"


def test_a_row_that_is_not_a_turn_is_dropped():
    """A future schema may store system or tool rows. Passing one through as a
    Turn would fail validation mid-request instead of being ignored.

    Compared as strings on purpose: `Role` in app.domain is the identity role
    (realtor/admin), and the conversation role is a different enum that the
    package deliberately does not re-export under the same name."""
    out = turns_from([{"role": "system", "message": "hello"}, {"role": "user", "message": "hi"}])
    assert [str(t.role) for t in out] == ["user"]


def test_an_empty_message_is_dropped():
    """A stream that died before any text leaves an empty assistant row."""
    assert turns_from([{"role": "assistant", "message": "", "sources": []}]) == []


def test_an_empty_answer_that_has_sources_still_travels():
    """Cards arrived, the text did not. The ids are still worth carrying."""
    out = turns_from([{"role": "assistant", "message": "", "sources": [{"id": "AK-1"}]}])
    assert out[0].content == "[projects: AK-1]"


def test_the_result_is_the_type_the_runtime_takes():
    assert all(isinstance(t, Turn) for t in turns_from([ANSWER]))


def test_nothing_in_no_rows():
    assert turns_from([]) == []


def test_the_source_line_is_never_cut_in_half():
    """The clamp used to run after the ids were appended, so a long answer could
    leave "[projects: AK-00" -- something that looks like a project reference
    and is not, which is the failure source_line exists to prevent."""
    from app.domain.conversation import MAX_CONTENT

    out = turns_from([{
        "role": "assistant",
        "message": "x" * (MAX_CONTENT + 500),
        "sources": [{"id": "AK-0021", "name": "Ivy Rogue"}],
    }])
    assert len(out[0].content) <= MAX_CONTENT
    assert out[0].content.endswith("[projects: AK-0021 Ivy Rogue]")
