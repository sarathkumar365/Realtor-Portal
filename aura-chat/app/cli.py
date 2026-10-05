"""`aura` -- a terminal client for Aura Chat.

Talks to the running service over HTTP, exactly as the PWA will: same login,
same token, same SSE contract. A CLI that reached into the app in-process would
keep working while the endpoint was broken, which is the one thing a client is
supposed to catch.

    aura login                     sign in with your portal ID
    aura                           interactive
    aura "detached under $1M"      one-shot
    aura --dev                     show every step of the interaction
    aura --client                  Client Mode, as a buyer would see it
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE = os.environ.get("AURA_BASE", "http://localhost:8000")
# Matches MAX_HISTORY_TURNS on the server; exceeding it is a 422, not a trim.
MAX_TURNS = 20
SESSION_FILE = Path(os.environ.get("AURA_HOME", Path.home() / ".aura")) / "session.json"

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
BLUE, GREEN, YELLOW, RED, GREY = (
    "\033[34m", "\033[32m", "\033[33m", "\033[31m", "\033[90m",
)


def _plain() -> bool:
    return not sys.stdout.isatty() or os.environ.get("NO_COLOR") is not None


def c(text: str, colour: str) -> str:
    return text if _plain() else f"{colour}{text}{RESET}"


# ---------------------------------------------------------------- session ----
def load_session() -> dict:
    try:
        return json.loads(SESSION_FILE.read_text())
    except Exception:
        return {}


def save_session(data: dict) -> None:
    """Token only, never the password, and readable by nobody else.

    The portal's token is a bearer credential: anyone holding it is that
    realtor until it expires. 0600 is the least this file deserves.
    """
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.touch(mode=0o600, exist_ok=True)
    SESSION_FILE.chmod(0o600)
    SESSION_FILE.write_text(json.dumps(data))


def token_from_anywhere(explicit: str | None) -> str:
    return explicit or os.environ.get("AURA_TOKEN") or load_session().get("token", "")


# ------------------------------------------------------------------ login ----
async def do_login(base: str) -> int:
    """Sign in against the portal, through this service.

    The password is typed by the person at the keyboard, sent once, and never
    written anywhere: what comes back and gets stored is the session token, the
    same one the phone app holds.
    """
    import getpass

    print(c("Aura Key portal sign-in", BOLD))
    user = input("Portal ID: ").strip()
    if not user:
        print(c("cancelled", GREY))
        return 1
    password = getpass.getpass("Password: ")
    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            res = await http.post(f"{base}/login", json={"user": user, "password": password})
        except httpx.HTTPError as exc:
            print(c(f"could not reach {base}: {exc}", RED))
            return 1
    # Parsed once, and defensively: --base can point at an SSO portal or a
    # captive proxy that answers 200 with an HTML page, and that is a failed
    # sign-in to report, not a traceback.
    try:
        body = res.json()
    except Exception:
        body = {}
    if res.status_code != 200 or not body.get("ok"):
        detail = body.get("error") or body.get("detail") or res.text[:200].strip()
        print(c(f"sign-in failed: {detail or res.status_code}", RED))
        return 1
    save_session({"token": body["token"], "name": body.get("name", user), "base": base})
    print(c(f"signed in as {body.get('name', user)}", GREEN), c(f"({SESSION_FILE})", GREY))
    return 0


def do_logout() -> int:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print(c("signed out", GREEN))
    else:
        print(c("not signed in", GREY))
    return 0


# ------------------------------------------------------------------- chat ----
async def ask(
    base: str,
    token: str,
    question: str,
    *,
    mode: str,
    history: list[dict],
    dev: bool,
    raw: bool,
    quiet: bool = False,
) -> tuple[str, list[dict]] | None:
    """One question. Returns (answer, cards), or None if it failed."""
    started = time.monotonic()
    answer, cards, step = [], [], started
    body = {"question": question, "mode": mode, "history": history}
    async with httpx.AsyncClient(timeout=180.0) as http:
        try:
            async with http.stream(
                "POST", f"{base}/chat", json=body, headers={"Authorization": f"Bearer {token}"}
            ) as res:
                if res.status_code == 401:
                    print(c("not signed in — run `aura login`", RED))
                    return None
                if res.status_code != 200:
                    await res.aread()
                    print(c(f"HTTP {res.status_code}: {res.text[:300]}", RED))
                    return None
                async for line in res.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if raw:
                        print(c(line, GREY))
                        continue
                    event = json.loads(line[6:])
                    step = _render(
                        event, answer, cards, dev=dev, step=step, started=started, quiet=quiet
                    )
        except httpx.HTTPError as exc:
            print(c(f"\nconnection failed: {exc}", RED))
            return None
    return "".join(answer), cards


def _render(
    event: dict, answer: list, cards: list, *, dev: bool, step: float, started: float,
    quiet: bool = False,
):
    kind = event.get("type")
    now = time.monotonic()
    ms = int((now - step) * 1000)

    if kind == "text":
        answer.append(event["text"])
        # `quiet` is --json: anything printed before the object would make the
        # output unparseable, which is the one thing that flag exists for.
        if not dev and not quiet:
            print(event["text"], end="", flush=True)
        return step  # text arrives in many chunks; do not time each one

    if quiet:
        if kind == "projects":
            cards.extend(event["projects"])
        elif kind == "error":
            print(c(f"{event['detail']}", RED), file=sys.stderr)
        return now

    if dev:
        if kind == "start":
            print(c(f"▸ mode      {event['mode']}", GREY))
        elif kind == "tool":
            args = {k: v for k, v in (event.get("args") or {}).items() if v not in ("", None, [])}
            print(c(f"▸ tool      {event['tool']}({_fmt_args(args)})", BLUE) + c(f"  +{ms}ms", GREY))
        elif kind == "tool_result":
            print(c(f"  └ returned {event.get('count', 0)}", GREY))
        elif kind == "projects":
            cards.extend(event["projects"])
        elif kind == "done":
            u = event.get("usage") or {}
            total = int((now - started) * 1000)
            print()
            print(c("".join(answer).strip(), RESET))
            print(
                c(
                    f"\n▸ done      {u.get('requests', 0)} model calls · "
                    f"{u.get('input_tokens', 0):,} in / {u.get('output_tokens', 0):,} out · "
                    f"{total}ms total",
                    GREY,
                )
            )
        elif kind == "error":
            print(c(f"\n▸ error     {event['detail']}", RED))
    else:
        if kind == "projects":
            cards.extend(event["projects"])
        elif kind == "error":
            print(c(f"\n{event['detail']}", RED))
    return now


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def show_cards(cards: list[dict], dev: bool) -> None:
    if not cards:
        return
    print(c(f"\n{len(cards)} project{'s' if len(cards) != 1 else ''}", BOLD))
    for p in cards:
        price = f"${p['starting_price']:,}" if p.get("starting_price") else c("no price", GREY)
        head = f"  {c(p.get('id', '?'), YELLOW)}  {c(p.get('name', '?'), BOLD)}"
        print(f"{head}  {c(p.get('city', ''), GREY)}  {price}")
        bits = [
            f"{k.replace('_', ' ')}: {v}"
            for k, v in p.items()
            if k in ("builder", "type", "bedrooms", "deposit_percent", "occupancy", "incentives")
            and v not in ("", None)
        ]
        if bits:
            print(c("     " + " · ".join(bits), GREY))
        if dev and p.get("source"):
            print(c(f"     source: {p['source']}", GREY))


def _bench(args) -> int:
    """`aura bench questions.csv` -- run a question set and write a report."""
    from pathlib import Path

    from app import bench

    token = token_from_anywhere(args.token)
    if not token:
        print(c("not signed in — run `aura login`", RED))
        return 1
    src = Path(args.question[1])
    if not src.exists():
        print(c(f"no such file: {src}", RED))
        return 1

    questions = bench.load(src)
    out = Path(args.out or src.parent)
    out.mkdir(parents=True, exist_ok=True)
    print(c(f"running {len(questions)} questions against {args.base}", BOLD))
    print(c("sequentially, so the timings mean something\n", GREY))

    results = asyncio.run(bench.run_all(args.base, token, questions, echo=print))
    summary = bench.summarise(results)
    report, log = out / "results.html", out / "results.csv"
    bench.write_html(results, summary, report)
    bench.write_csv(results, log)

    print()
    print(c(f"  {summary['passed']}/{summary['answered']} mechanical checks passed"
            + (f"  ({summary['total'] - summary['answered']} not answered)"
               if summary["answered"] < summary["total"] else ""), BOLD))
    if summary["failed"]:
        print(c(f"  {summary['failed']} failed", RED))
    if summary["errors"]:
        print(c(f"  {summary['errors']} errored", RED))
    print(c(f"  median {summary['median_s']:.1f}s · slowest {summary['slowest_s']:.1f}s"
            f" · {summary['over_10s']} over 10s", GREY))
    print(c(f"  {summary['input_tokens']:,} in / {summary['output_tokens']:,} out tokens", GREY))
    print()
    print(c(f"  report  {report}", GREEN))
    print(c(f"  log     {log}", GREEN))
    print(c("\n  Green means nothing measurable is wrong, not that the answer is true.\n"
            "  The verdict column is for a person who knows the inventory.", GREY))
    return 1 if (summary["failed"] or summary["errors"]) else 0


EPILOG = """\
first time
  aura login                          sign in with your portal ID and password
                                      (only the returned token is stored, in
                                       ~/.aura/session.json, mode 0600)
  aura logout                         forget the saved session

benchmarking
  aura bench benchmarks/questions.csv run a question set, write results.html
                                      and results.csv beside it

asking
  aura                                interactive session, with follow-ups
  aura "detached under $1M"           ask once and exit
  aura --client "tell me about Kai"   as a buyer would see it: commission,
                                      internal notes and builder contacts removed
  aura --dev "what changed?"          show each tool call, its arguments,
                                      timings and token usage
  aura --json "townhomes" | jq .      one JSON object, nothing else on stdout

in an interactive session
  /new     forget this conversation      /dev    toggle the detailed view
  /mode    switch realtor <-> client     /quit   leave

environment
  AURA_BASE    service URL            (default http://localhost:8000)
  AURA_TOKEN   use this token         (overrides the saved session)
  AURA_HOME    where the session lives (default ~/.aura)
  NO_COLOR     plain output

the service must be running:
  .venv/bin/uvicorn app.main:app --reload
"""


# ------------------------------------------------------------------- main ----
async def repl(base: str, token: str, *, mode: str, dev: bool, raw: bool) -> int:
    who = load_session().get("name", "")
    print(c(f"Aura Chat{' — ' + who if who else ''}", BOLD), c(f"· {mode} mode · {base}", GREY))
    print(c("ask a question, or /help", GREY))
    history: list[dict] = []
    while True:
        try:
            q = input(c("\n> ", BLUE)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q in ("/quit", "/exit", "/q"):
            return 0
        if q == "/help":
            print(c("  /new    forget this conversation\n"
                    "  /mode   switch realtor <-> client\n"
                    "  /dev    toggle the detailed view\n"
                    "  /quit", GREY))
            continue
        if q == "/new":
            history = []
            print(c("  conversation cleared", GREY))
            continue
        if q == "/mode":
            mode = "client" if mode == "realtor" else "realtor"
            print(c(f"  {mode} mode", GREY))
            continue
        if q == "/dev":
            dev = not dev
            print(c(f"  dev {'on' if dev else 'off'}", GREY))
            continue
        print()
        got = await ask(base, token, q, mode=mode, history=history, dev=dev, raw=raw)
        if got is None:
            continue
        answer, cards = got
        show_cards(cards, dev)
        # Only a turn that actually produced an answer joins the history. A
        # failed one would go in as an empty assistant message, which some
        # providers reject outright -- one failure poisoning every question
        # after it -- and which teaches the model that answering with nothing
        # is normal. --raw never fills `answer` either, for the same reason.
        if answer.strip():
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": answer})
            # Trimmed to the cap the server enforces, so a long session cannot
            # start failing validation.
            history[:] = history[-MAX_TURNS:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="aura",
        description="Ask Aura about Aura Key Realty's pre-construction projects.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # login and logout are positional rather than flags, and argparse will not
    # advertise them on its own -- so the epilog does. A user who cannot find
    # how to sign in has no way into the tool at all.
    ap.add_argument(
        "question",
        nargs="*",
        metavar="QUESTION | login | logout",
        help="a question to ask once, or `login` / `logout`; omit for an interactive session",
    )
    ap.add_argument("--dev", action="store_true", help="show tools, timings and token usage")
    ap.add_argument("--raw", action="store_true", help="dump the SSE events verbatim")
    ap.add_argument("--client", action="store_true", help="Client Mode, as a buyer would see it")
    ap.add_argument("--token", help="use this token instead of the saved session")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"service URL (default {DEFAULT_BASE})")
    ap.add_argument("--json", action="store_true", help="print one JSON object and exit")
    ap.add_argument("--out", help="bench: where to write the report (default benchmarks/)")
    args = ap.parse_args(argv)

    # A single bare word, not merely the first word: `aura login details for
    # Great Gulf` is a question, and answering it with an unexpected password
    # prompt is the least welcome thing a tool can do.
    only = args.question[0] if len(args.question) == 1 else ""
    if only == "login":
        return asyncio.run(do_login(args.base))
    if only == "logout":
        return do_logout()
    # Same guard as login and logout above: the word plus exactly one path, so
    # `aura bench mark projects against Oakville` stays a question.
    if len(args.question) == 2 and args.question[0] == "bench":
        return _bench(args)
    if only == "bench":
        print(c("usage: aura bench <questions.csv> [--out DIR]", RED))
        return 1

    token = token_from_anywhere(args.token)
    if not token:
        print(c("not signed in — run `aura login`", RED))
        return 1
    mode = "client" if args.client else "realtor"

    if not args.question:
        return asyncio.run(repl(args.base, token, mode=mode, dev=args.dev, raw=args.raw))

    question = " ".join(args.question)
    got = asyncio.run(
        ask(
            args.base, token, question, mode=mode, history=[],
            dev=args.dev, raw=args.raw, quiet=args.json,
        )
    )
    if got is None:
        return 1
    answer, cards = got
    if args.json:
        print(json.dumps({"question": question, "answer": answer, "projects": cards}, indent=2))
        return 0
    show_cards(cards, args.dev)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
