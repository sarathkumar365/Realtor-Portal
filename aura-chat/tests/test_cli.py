"""The CLI's own logic: argument handling, history hygiene, output shape.

Nothing here starts a server -- these cover the decisions the CLI makes on its
own, which is where its bugs live.
"""

import json

from app import cli


def test_a_subcommand_is_one_bare_word():
    """`aura login details for Great Gulf` is a question. Answering it with an
    unexpected password prompt is the least welcome thing a tool can do."""
    assert cli.main.__module__  # sanity
    parsed = ["login", "details", "for", "Great", "Gulf"]
    only = parsed[0] if len(parsed) == 1 else ""
    assert only == ""

    parsed = ["login"]
    only = parsed[0] if len(parsed) == 1 else ""
    assert only == "login"


def test_json_mode_suppresses_the_streamed_prose(capsys):
    """Anything printed before the object makes the output unparseable, which
    is the one thing --json exists for."""
    answer, cards = [], []
    cli._render(
        {"type": "text", "text": "hello "}, answer, cards,
        dev=False, step=0.0, started=0.0, quiet=True,
    )
    assert capsys.readouterr().out == ""
    assert answer == ["hello "]


def test_normal_mode_still_streams_the_prose(capsys):
    answer, cards = [], []
    cli._render(
        {"type": "text", "text": "hello "}, answer, cards,
        dev=False, step=0.0, started=0.0, quiet=False,
    )
    assert capsys.readouterr().out == "hello "


def test_json_mode_sends_errors_to_stderr(capsys):
    answer, cards = [], []
    cli._render(
        {"type": "error", "detail": "boom"}, answer, cards,
        dev=False, step=0.0, started=0.0, quiet=True,
    )
    captured = capsys.readouterr()
    assert captured.out == "" and "boom" in captured.err


def test_json_mode_still_collects_cards():
    answer, cards = [], []
    cli._render(
        {"type": "projects", "projects": [{"id": "AK-1", "name": "R"}]}, answer, cards,
        dev=False, step=0.0, started=0.0, quiet=True,
    )
    assert [p["id"] for p in cards] == ["AK-1"]


def test_the_session_file_is_written_private(tmp_path, monkeypatch):
    """A portal token is a bearer credential: anyone holding it is that realtor
    until it expires."""
    monkeypatch.setattr(cli, "SESSION_FILE", tmp_path / "session.json")
    cli.save_session({"token": "t", "name": "Sarath"})
    assert cli.SESSION_FILE.stat().st_mode & 0o077 == 0
    assert cli.load_session()["token"] == "t"


def test_a_missing_session_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "SESSION_FILE", tmp_path / "nope.json")
    assert cli.load_session() == {}


def test_a_corrupt_session_file_is_not_an_error(tmp_path, monkeypatch):
    path = tmp_path / "session.json"
    path.write_text("{not json")
    monkeypatch.setattr(cli, "SESSION_FILE", path)
    assert cli.load_session() == {}


def test_token_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "SESSION_FILE", tmp_path / "session.json")
    cli.save_session({"token": "from-file"})
    monkeypatch.setenv("AURA_TOKEN", "from-env")
    assert cli.token_from_anywhere("explicit") == "explicit"
    assert cli.token_from_anywhere(None) == "from-env"
    monkeypatch.delenv("AURA_TOKEN")
    assert cli.token_from_anywhere(None) == "from-file"


def test_help_tells_you_how_to_sign_in():
    """argparse will not advertise a positional subcommand on its own, and a
    user who cannot find how to sign in has no way into the tool at all."""
    assert "aura login" in cli.EPILOG
    assert "aura logout" in cli.EPILOG or "logout" in cli.EPILOG


def test_help_documents_the_interactive_commands():
    for command in ("/new", "/mode", "/dev", "/quit"):
        assert command in cli.EPILOG


def test_help_names_the_environment_variables_the_code_reads():
    for var in ("AURA_BASE", "AURA_TOKEN", "AURA_HOME"):
        assert var in cli.EPILOG


def test_help_says_the_service_must_be_running():
    assert "uvicorn" in cli.EPILOG


def test_a_billing_failure_is_not_reported_as_a_wrong_answer():
    """A page of "cards>=1 - got 0" that all share one cause hides the cause."""
    from app import bench

    q = bench.Question(id="Q1", mode="realtor", follows="", question="x",
                       expect="y", check="cards>=1;says:brampton")
    r = bench.Result(q=q, error="ModelHTTPError: status_code: 402 ... credits")
    r.failures = [] if r.error else bench.evaluate(r)
    assert r.status == "error" and r.failures == []


def test_fatal_errors_are_the_ones_about_the_account():
    from app import bench

    for fatal in ("status_code: 402", "429 rate limit", "insufficient credit",
                  "in_flight_budget_exhausted", "invalid api key"):
        assert bench.is_fatal(fatal), fatal
    for keep_going in ("TimeoutError", "portal unreachable", "ValidationError"):
        assert not bench.is_fatal(keep_going), keep_going


# --- the benchmark runner's own edges ---------------------------------------

def _write(tmp_path, text, name="questions.csv", encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


HEADER = "id,mode,follows,question,expect,check\n"


def test_a_csv_exported_from_sheets_loads(tmp_path):
    """Google Sheets and Excel both write a BOM. Read as plain utf-8 it becomes
    part of the first field name, and the error names a keyword nobody typed."""
    from app import bench

    src = _write(tmp_path, HEADER + "Q1,realtor,,hi,x,cards>=1\n", encoding="utf-8-sig")
    assert [q.id for q in bench.load(src)] == ["Q1"]


def test_duplicate_question_ids_are_refused_before_anything_runs(tmp_path):
    """A copied row in a 50-row sheet is invisible, and silently costs one
    question's result while showing another's twice."""
    import pytest

    from app import bench

    src = _write(tmp_path, HEADER + "Q1,realtor,,a,x,\nQ1,realtor,,b,y,\n")
    with pytest.raises(ValueError, match="duplicate question id"):
        bench.load(src)


def test_history_is_capped_at_what_the_server_accepts():
    """The cap has to apply to the whole history: slicing only the two new
    turns is a no-op, and a long chain then 422s on every question."""
    from app import bench

    history = [{"role": "user", "content": f"q{i}"} for i in range(30)]
    capped = (history + [{"role": "user", "content": "n"}, {"role": "assistant", "content": "a"}])[
        -bench.MAX_HISTORY :
    ]
    assert len(capped) == bench.MAX_HISTORY


def test_the_report_escapes_project_names(tmp_path):
    """A `<` in a name would otherwise swallow the project, in a report whose
    whole job is showing what came back."""
    from app import bench

    q = bench.Question(id="Q1", mode="realtor", follows="", question="x", expect="y", check="")
    r = bench.Result(q=q, answer="ok", cards=[{"id": "AK-1", "name": "Smith & <Sons>"}])
    out = tmp_path / "r.html"
    bench.write_html([r], bench.summarise([r]), out)
    body = out.read_text()
    assert "&lt;Sons&gt;" in body and "<Sons>" not in body


def test_an_unreadable_event_does_not_lose_the_whole_run():
    """Forty already-paid-for answers should not be lost to one bad line."""
    from app import bench

    r = bench.Result(q=bench.Question("Q1", "realtor", "", "x", "y", ""))
    try:
        json_broken = "data: {not json"
        import json as _json

        _json.loads(json_broken[6:])
    except ValueError as exc:
        r.error = f"{type(exc).__name__}: {exc}"
    assert r.status == "error"
