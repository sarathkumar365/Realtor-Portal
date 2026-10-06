"""`aura bench` -- run a question set and score what can be scored.

Two kinds of judgement live in a benchmark, and conflating them is how a
benchmark stops being trusted:

* **Mechanical.** Did any projects come back? Did the right one? Did it take
  more than ten seconds? Did a forbidden word appear in a Client Mode answer?
  A machine settles these, identically every run.
* **Human.** Is $899,900 the right price for Reva Westfield? Only a person who
  knows the inventory can say.

So this scores the first kind and leaves the second to a verdict column. It
never guesses at correctness, because a benchmark that marks a wrong answer
green is worse than no benchmark: it removes the reason to look.
"""

import asyncio
import csv
import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Matches MAX_HISTORY_TURNS on the server, where exceeding it is a 422.
MAX_HISTORY = 20


@dataclass(slots=True)
class Question:
    id: str
    mode: str
    follows: str
    question: str
    expect: str
    check: str


@dataclass(slots=True)
class Result:
    q: Question
    answer: str = ""
    cards: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    error: str = ""
    failures: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.failures:
            return "fail"
        return "pass"


def load(path: Path) -> list[Question]:
    """The questions, from a CSV a person edits.

    utf-8-sig, because the expected authoring path is Google Sheets and both it
    and Excel write a byte-order mark when exporting. Read as plain utf-8 that
    mark becomes part of the first field name, and the failure is a TypeError
    about a keyword argument nobody typed.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        questions = [Question(**row) for row in csv.DictReader(f)]

    # --- 4. Ids are how a follow-up finds its chain and how results are matched
    # back to rows, so a duplicate is not a cosmetic problem: the second run
    # overwrites the first, the report shows one answer twice, and the other
    # question's result is gone. Refusing to start is cheaper than a report that
    # quietly disagrees with itself.
    seen: dict[str, int] = {}
    for q in questions:
        seen[q.id] = seen.get(q.id, 0) + 1
    repeated = sorted(qid for qid, n in seen.items() if n > 1)
    if repeated:
        raise ValueError(f"duplicate question id(s) in {path.name}: {', '.join(repeated)}")
    return questions


# ------------------------------------------------------------------ checks ---
def evaluate(r: Result) -> list[str]:
    """Every failed assertion, in words. Empty means nothing mechanical is wrong
    -- which is not the same as the answer being right."""
    out: list[str] = []
    answer = r.answer.lower()
    ids = {c.get("id", "") for c in r.cards}
    called = {t.get("tool", "") for t in r.tools}

    for raw in (r.q.check or "").split(";"):
        rule = raw.strip()
        if not rule:
            continue
        try:
            if rule.startswith("cards"):
                op, want = _split_cmp(rule[len("cards"):])
                n = len(r.cards)
                if not _cmp(n, op, want):
                    out.append(f"{rule} — got {n}")
            elif rule.startswith("no_id:"):
                bad = rule[6:]
                if bad in ids:
                    out.append(f"{bad} should not have been returned")
            elif rule.startswith("id:"):
                want = rule[3:]
                if want not in ids:
                    out.append(f"{want} missing (got {sorted(ids) or 'none'})")
            elif rule.startswith("not_says:"):
                bad = rule[9:].lower()
                if bad in answer:
                    out.append(f"answer contains {bad!r}")
            elif rule.startswith("says:"):
                want = rule[5:].lower()
                if want not in answer:
                    out.append(f"answer does not contain {want!r}")
            elif rule.startswith("tool:"):
                want = rule[5:]
                if want not in called:
                    out.append(f"{want} was not called (called {sorted(called) or 'nothing'})")
            elif rule.startswith("under:"):
                limit = float(rule[6:])
                if r.seconds > limit:
                    out.append(f"took {r.seconds:.1f}s, over {limit:.0f}s")
            else:
                out.append(f"unknown check {rule!r}")
        except Exception as exc:  # a malformed rule must not abort the run
            out.append(f"bad check {rule!r}: {exc}")
    return out


def _split_cmp(rest: str) -> tuple[str, float]:
    for op in (">=", "<=", "==", ">", "<"):
        if rest.startswith(op):
            return op, float(rest[len(op):])
    raise ValueError("expected >=, <=, ==, > or <")


def _cmp(n: float, op: str, want: float) -> bool:
    return {">=": n >= want, "<=": n <= want, "==": n == want,
            ">": n > want, "<": n < want}[op]


# --------------------------------------------------------------------- run ---
async def run_one(
    http: httpx.AsyncClient, base: str, token: str, q: Question, history: list[dict]
) -> Result:
    r = Result(q=q)
    started = time.monotonic()
    body = {"question": q.question, "mode": q.mode or "realtor", "history": history}
    try:
        async with http.stream(
            "POST", f"{base}/chat", json=body, headers={"Authorization": f"Bearer {token}"}
        ) as res:
            if res.status_code != 200:
                await res.aread()
                r.error = f"HTTP {res.status_code}: {res.text[:200]}"
                return r
            async for line in res.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    ev = json.loads(line[6:])
                except ValueError:
                    # A keep-alive comment, a split write, or an event shape we
                    # do not know yet. Losing forty already-paid-for answers to
                    # one bad line is the worse outcome, so note it and read on.
                    r.error = r.error or f"unreadable event: {line[:120]}"
                    continue
                kind = ev.get("type")
                if kind == "text":
                    r.answer += ev["text"]
                elif kind == "tool":
                    r.tools.append({"tool": ev["tool"], "args": ev.get("args") or {}})
                elif kind == "tool_result":
                    r.tools.append({"tool": ev.get("tool", ""), "count": ev.get("count")})
                elif kind == "projects":
                    r.cards = ev["projects"]
                elif kind == "done":
                    r.usage = ev.get("usage") or {}
                elif kind == "error":
                    r.error = ev["detail"]
    except (httpx.HTTPError, ValueError) as exc:
        r.error = f"{type(exc).__name__}: {exc}"
    r.seconds = time.monotonic() - started
    # Checks are only meaningful if the question was actually answered. A run
    # that died on a 402 has no cards for reasons that have nothing to do with
    # the model, and reporting "cards>=1 - got 0" blames Aura for a billing
    # problem -- which is how a benchmark stops being believed.
    r.failures = [] if r.error else evaluate(r)
    return r


# Errors that mean "stop, this is not about the answers": no credit, rate
# limited, no key. Running the remaining questions produces a page of failures
# that all share one cause and hide it.
_ABORT = ("402", "429", "credit", "rate limit", "quota", "in_flight", "api key", "unauthorized")


def is_fatal(error: str) -> bool:
    low = error.lower()
    return any(marker in low for marker in _ABORT)


async def run_all(base: str, token: str, questions: list[Question], *, echo=print) -> list[Result]:
    """Sequentially, on purpose.

    Concurrency would race on the portal's per-action cache-busting gate and
    make timings meaningless, and the 10-second target is measured per question
    with nothing else competing for the model.
    """
    results: dict[str, Result] = {}
    asked = 0
    # A follow-up must be asked in the context of what came before it, so a
    # question naming `follows` inherits that chain's history.
    chains: dict[str, list[dict]] = {}

    async with httpx.AsyncClient(timeout=180.0) as http:
        for q in questions:
            history = list(chains.get(q.follows, [])) if q.follows else []
            r = await run_one(http, base, token, q, history)
            results[q.id] = r
            asked += 1
            if r.error and is_fatal(r.error):
                echo(f"  STOP {q.id}  {r.error[:160]}")
                echo("")
                echo("  Stopped: that failure is about the account, not the answers.")
                echo(f"  {len(questions) - asked} questions not run.")
                for skipped in questions[asked:]:
                    results[skipped.id] = Result(q=skipped, error="not run")
                break
            if r.answer.strip():
                # Parenthesised: without them the slice takes the last 20 of the
                # two-element literal, which is a no-op, and a long chain grows
                # past the 20 turns /chat accepts -- every question after that
                # returning 422.
                chains[q.id] = (
                    history
                    + [
                        {"role": "user", "content": q.question},
                        {"role": "assistant", "content": r.answer},
                    ]
                )[-MAX_HISTORY:]
            mark = {"pass": "ok  ", "fail": "FAIL", "error": "ERR "}[r.status]
            echo(f"  {mark} {q.id}  {r.seconds:5.1f}s  {len(r.cards):>2} cards  {q.question[:52]}")
            for f in r.failures:
                echo(f"         · {f}")
    return [results[q.id] for q in questions]


# ------------------------------------------------------------------ report ---
def summarise(results: list[Result]) -> dict[str, Any]:
    passed = sum(1 for r in results if r.status == "pass")
    times = sorted(r.seconds for r in results if not r.error and r.seconds > 0)
    over = [r for r in results if r.seconds > 10 and not r.error]
    return {
        "total": len(results),
        "answered": sum(1 for r in results if not r.error),
        "passed": passed,
        "failed": sum(1 for r in results if r.status == "fail"),
        "errors": sum(1 for r in results if r.status == "error"),
        "median_s": times[len(times) // 2] if times else 0.0,
        "slowest_s": times[-1] if times else 0.0,
        "over_10s": len(over),
        "input_tokens": sum(r.usage.get("input_tokens", 0) for r in results),
        "output_tokens": sum(r.usage.get("output_tokens", 0) for r in results),
        "model_calls": sum(r.usage.get("requests", 0) for r in results),
    }


def write_html(results: list[Result], summary: dict, path: Path) -> None:
    """One self-contained page. The verdict column is empty on purpose: the
    mechanical checks cannot tell you whether an answer is *true*, and a report
    that pretended otherwise would be the reason nobody reads it."""
    e = html.escape

    def row(r: Result) -> str:
        # Escaped like every other value here: a `<` in a project name would
        # otherwise swallow it, in a report whose whole job is showing what
        # came back.
        cards = ", ".join(
            f"{e(str(c.get('id', '?')))} {e(str(c.get('name', '')))}" for c in r.cards[:6]
        ) or "<i>none</i>"
        if len(r.cards) > 6:
            cards += f" … +{len(r.cards) - 6}"
        tools = " → ".join(
            f"{t['tool']}({_args(t.get('args'))})" if "args" in t else f"↩ {t.get('count')}"
            for t in r.tools
        ) or "<i>no tool call</i>"
        notes = "".join(f"<li>{e(f)}</li>" for f in r.failures)
        if r.error:
            notes = f"<li class='err'>{e(r.error)}</li>" + notes
        return f"""<tr class="{r.status}">
  <td class="id">{e(r.q.id)}<br><span class="mode">{e(r.q.mode)}</span></td>
  <td class="st"><span class="badge {r.status}">{r.status}</span><br>
      <span class="t">{r.seconds:.1f}s</span></td>
  <td><div class="q">{e(r.q.question)}</div>
      <div class="exp"><b>expected:</b> {e(r.q.expect)}</div></td>
  <td><div class="ans">{e(r.answer) or "<i>no answer</i>"}</div>
      <div class="meta">{cards}</div>
      <div class="meta tools">{e(tools)}</div>
      {f'<ul class="fails">{notes}</ul>' if notes else ""}</td>
  <td class="verdict"></td>
</tr>"""

    s = summary
    open_tag = "<" + "style>"
    css = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#6b7280;--line:#e5e7eb;
--pass:#15803d;--fail:#b91c1c;--err:#a16207;--accent:#8a5b1c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1400px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 22px}
.kpis{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin-bottom:24px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .l{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute)}
.kpi .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:10px;overflow:hidden}
th{text-align:left;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
color:var(--mute);padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}
tr.fail{background:#fef6f6}tr.error{background:#fffbeb}
.id{font-family:ui-monospace,monospace;font-size:12px;white-space:nowrap}
.mode{color:var(--mute);font-size:11px}
.st{white-space:nowrap}.t{color:var(--mute);font-size:12px;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;
font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.badge.pass{background:#dcfce7;color:var(--pass)}
.badge.fail{background:#fee2e2;color:var(--fail)}
.badge.error{background:#fef3c7;color:var(--err)}
.q{font-weight:600;margin-bottom:6px}
.exp{color:var(--mute);font-size:12.5px}
.ans{white-space:pre-wrap;margin-bottom:8px}
.meta{color:var(--mute);font-size:12px;font-family:ui-monospace,monospace;
word-break:break-word;margin-bottom:3px}
.tools{color:#1f5f9e}
.fails{margin:8px 0 0;padding-left:18px;color:var(--fail);font-size:12.5px}
.fails .err{color:var(--err)}
.verdict{width:120px;background:#fafafa}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:10px;padding:14px 16px;margin-bottom:22px;font-size:13.5px}
@media print{.verdict{border:1px solid #999}}
"""
    body = "\n".join(row(r) for r in results)
    path.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Aura Chat — benchmark</title>{open_tag}{css}</style></head><body><div class="wrap">
<h1>Aura Chat — benchmark</h1>
<p class="sub">{s['answered']} of {s['total']} questions answered · {s['model_calls']} model calls ·
{s['input_tokens']:,} in / {s['output_tokens']:,} out</p>
<div class="kpis">
  <div class="kpi"><div class="l">checks passed</div><div class="v">{s['passed']}/{s['answered']}</div></div>
  <div class="kpi"><div class="l">failed</div><div class="v">{s['failed']}</div></div>
  <div class="kpi"><div class="l">errors</div><div class="v">{s['errors']}</div></div>
  <div class="kpi"><div class="l">median</div><div class="v">{s['median_s']:.1f}s</div></div>
  <div class="kpi"><div class="l">slowest</div><div class="v">{s['slowest_s']:.1f}s</div></div>
  <div class="kpi"><div class="l">over 10s</div><div class="v">{s['over_10s']}</div></div>
</div>
<div class="note"><b>These are the mechanical checks only.</b> A green row means
nothing measurable is wrong — not that the answer is true. Whether $899,900 is
the right price for a project is a question only somebody who knows the
inventory can settle, which is what the verdict column is for. Print this and
fill it in, or read it beside the sheet.</div>
<table><thead><tr><th>#</th><th>result</th><th>question &amp; expectation</th>
<th>what Aura said</th><th>verdict</th></tr></thead>
<tbody>{body}</tbody></table>
</div></body></html>""")


def _args(a: dict | None) -> str:
    if not a:
        return ""
    return ", ".join(f"{k}={v!r}" for k, v in a.items() if v not in ("", None, []))


def write_csv(results: list[Result], path: Path) -> None:
    """The columns AUR-76 asks for, so the log can go straight into a sheet."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "mode", "question", "expected", "aura answer", "projects",
            "tools", "seconds", "checks failed", "correct?", "correct source?",
            "latest data?", "issue",
        ])
        for r in results:
            w.writerow([
                r.q.id, r.q.mode, r.q.question, r.q.expect, r.answer,
                " | ".join(f"{c.get('id','?')} {c.get('name','')}" for c in r.cards),
                " → ".join(t.get("tool", "") for t in r.tools if "args" in t),
                f"{r.seconds:.1f}",
                "; ".join(r.failures) or ("ERROR: " + r.error if r.error else ""),
                "", "", "", "",
            ])
