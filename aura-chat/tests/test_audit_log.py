"""AUR-20: who asked what, which tools ran, what came back.

Asserted through captured stdout, not caplog: caplog attaches its own handler,
which is exactly what hid the missing one last time.
"""

import json
import logging
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.domain import Project
from app.main import configure_logging
from tests.fakes import FakeProjectRepo, make_token
from tests.test_chat_endpoint import StubRuntime

TOKEN = make_token("sarath")


@contextmanager
def to_stdout():
    """The `aura` logger as production has it: one stdout handler, no caplog.

    A context manager, not a fixture: pytest gives the setup and call phases
    different capture objects, so the handler must be built in the test body.
    """
    aura = logging.getLogger("aura")
    saved, level, prop = aura.handlers[:], aura.level, aura.propagate
    for h in saved:
        aura.removeHandler(h)
    configure_logging()
    try:
        yield
    finally:
        for h in aura.handlers[:]:
            aura.removeHandler(h)
        for h in saved:
            aura.addHandler(h)
        aura.setLevel(level)
        aura.propagate = prop


def audit_lines(out: str) -> list[dict]:
    return [
        json.loads(line[line.index("{"):])
        for line in out.splitlines()
        if "aura.audit" in line and "{" in line
    ]


def ask(app, runtime=None, **body):
    app.state.container.runtime = runtime or StubRuntime()
    app.state.container.projects = FakeProjectRepo([Project(name="R", city="C")])
    with TestClient(app) as client:
        return client.post(
            "/chat",
            json={"question": "hi", **body},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )


def test_every_question_leaves_one_line(app, capsys):
    with to_stdout():
        ask(app)
    lines = audit_lines(capsys.readouterr().out)
    assert len(lines) == 1
    assert lines[0]["user"] == "sarath"
    assert lines[0]["question"] == "hi"
    assert lines[0]["status"] == "ok"


def test_the_line_carries_the_request_id(app, capsys):
    """The only thing that ties a log line to what a realtor saw on screen."""
    with to_stdout():
        r = ask(app)
    line = audit_lines(capsys.readouterr().out)[0]
    assert line["rid"] == r.headers["X-Request-Id"]


def test_the_mode_is_recorded(app, capsys):
    """Which mode an answer was given in is the first question anyone asks
    when a disclosure is reported."""
    with to_stdout():
        ask(app, mode="client")
    assert audit_lines(capsys.readouterr().out)[0]["mode"] == "client"


def test_the_answer_text_never_reaches_the_log(app, capsys):
    """An answer can quote commission; the question cannot."""
    runtime = StubRuntime(
        [{"type": "text", "text": "commission is 5%"}, {"type": "done"}]
    )
    with to_stdout():
        ask(app, runtime=runtime)
    out = capsys.readouterr().out
    # The line has to be there, or "the answer is absent" is true of an empty
    # buffer and this proves nothing.
    assert audit_lines(out)[0]["question"] == "hi"
    assert "commission is 5%" not in out


def test_the_tools_that_ran_are_recorded_with_their_counts(app, capsys):
    runtime = StubRuntime(
        [
            {"type": "tool", "tool": "search_projects", "args": {}},
            {"type": "tool_result", "tool": "search_projects", "count": 4},
            {"type": "text", "text": "ok"},
            {"type": "done"},
        ]
    )
    with to_stdout():
        ask(app, runtime=runtime)
    assert audit_lines(capsys.readouterr().out)[0]["tools"] == [
        {"t": "search_projects", "n": 4}
    ]


def test_token_usage_is_recorded(app, capsys):
    """The cost of an answer, on the line that says who asked for it."""
    runtime = StubRuntime(
        [{"type": "done", "usage": {"input_tokens": 900, "output_tokens": 120}}]
    )
    with to_stdout():
        ask(app, runtime=runtime)
    line = audit_lines(capsys.readouterr().out)[0]
    assert (line["tokens_in"], line["tokens_out"]) == (900, 120)


def test_a_failed_answer_is_logged_as_one(app, capsys):
    class Exploding:
        async def stream(self, **kw):
            raise RuntimeError("model is down")
            yield  # pragma: no cover

        async def healthy(self):
            return True

    with to_stdout():
        ask(app, runtime=Exploding())
    line = audit_lines(capsys.readouterr().out)[0]
    assert line["status"] == "error"
    assert "model is down" in line["error"]


def test_a_missing_runtime_still_leaves_a_line(app, capsys):
    """An early return is still an answer a realtor did not get."""
    app.state.container.runtime = None
    app.state.container.projects = FakeProjectRepo([])
    with to_stdout(), TestClient(app) as client:
        client.post(
            "/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"}
        )
    line = audit_lines(capsys.readouterr().out)[0]
    assert line["status"] == "error"


def test_a_refused_token_is_logged_without_the_token(app, capsys):
    """The address is the signal; the credential is not."""
    app.state.container.auth.allow = False
    with to_stdout(), TestClient(app) as client:
        client.get("/me", headers={"Authorization": "Bearer sekrit-token-value"})
    out = capsys.readouterr().out
    assert "auth refused" in out
    assert "sekrit-token-value" not in out
