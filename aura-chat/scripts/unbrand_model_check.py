"""Run the unbrand step (sort, pick, execute, judge, repair) on a real builder PDF, by hand.

The model check from PHASES.md. Not a pytest: it calls OpenRouter and reads
real PDFs from .local/, and writes what it produces under .local/unbrand/ as it
goes, so a run that fails late keeps every earlier round and model call. The
OpenRouter key comes from .env and is never printed.

    .venv/bin/python scripts/unbrand_model_check.py brochure.pdf \\
        --builder "Arista Homes" --project SouthCal [--short AH] \\
        [--instructions "drop the sales centre map"] [--expect-pages 8-12,15-22] \\
        [--sort-model ...] [--pick-model ...] [--judge-model ...] [--repair-model ...]

--expect-pages names the source pages a person kept (the skill's own output of the
spike brochure kept 8-12 and 15-22); the run reports how its pages differ.

Output, under .local/unbrand/<pdf name>/<sort model>+<pick model>/:
    calls.jsonl     one line per model call: prompt text, raw answer, tokens, cost
    round-N/        cleaned.pdf, actions.json, verify.txt, judge.txt as each round ends
    run.json        totals, once the run finishes
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf

from app.capabilities.unbrander.adapters.models_langchain import LangChainUnbrandModels
from app.capabilities.unbrander.adapters.pdf_edit_pymupdf import PyMuPdfEditor
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.domain import Brief, Check, Finding, HitList, Severity
from app.capabilities.unbrander.unbrand import RoundResult, unbrand_document
from app.config import load

ROOT = Path(__file__).resolve().parent.parent


async def main() -> int:
    config = load()
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--builder", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--short", action="append", default=[])
    parser.add_argument("--instructions")
    parser.add_argument("--expect-pages", type=_page_list)
    parser.add_argument("--sort-model", default=config.unbrander_sort_model)
    parser.add_argument("--pick-model", default=config.unbrander_pick_model)
    parser.add_argument("--judge-model", default=config.unbrander_judge_model)
    parser.add_argument("--repair-model", default=config.unbrander_repair_model)
    parser.add_argument("--thinking", action="append", default=[], metavar="ROLE=EFFORT",
                        help="e.g. pick=off or sort=low; overrides unbrander_thinking")
    parser.add_argument("--max-rounds", type=int, default=config.unbrander_max_rounds)
    args = parser.parse_args()
    if not config.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set in .env")
        return 2

    pdf = Path(args.pdf).read_bytes()
    with pymupdf.open(stream=pdf) as doc:
        pages = doc.page_count
    thinking = dict(config.unbrander_thinking)
    thinking.update(item.split("=", 1) for item in args.thinking)
    run_name = f"{args.sort_model}+{args.pick_model}".replace("/", "_")
    for role, model in (("judge", args.judge_model), ("repair", args.repair_model)):
        if model != args.pick_model:  # runs that differ only here must not share a folder
            run_name += f"+{role}-{model.replace('/', '_')}"
    if thinking:
        run_name += "+" + ",".join(f"{role}-{effort}" for role, effort in sorted(thinking.items()))
    out = ROOT / ".local" / "unbrand" / Path(args.pdf).stem / run_name
    out.mkdir(parents=True, exist_ok=True)
    (out / "calls.jsonl").unlink(missing_ok=True)

    brief = Brief(hits=HitList(builder=args.builder, project=args.project,
                               short_forms=args.short),
                  page_count=pages, instructions=args.instructions)
    models = LangChainUnbrandModels(api_key=config.openrouter_api_key,
                                    sort_model=args.sort_model, pick_model=args.pick_model,
                                    judge_model=args.judge_model, repair_model=args.repair_model,
                                    thinking=thinking,
                                    call_log=out / "calls.jsonl")

    def save_round(result: RoundResult) -> None:
        folder = out / f"round-{result.number}"
        folder.mkdir(exist_ok=True)
        (folder / "cleaned.pdf").write_bytes(result.pdf)
        (folder / "actions.json").write_text(json.dumps(
            [outcome.model_dump(mode="json") for outcome in result.outcomes], indent=2))
        (folder / "verify.txt").write_text(_lines(result.report.findings))
        (folder / "judge.txt").write_text(_lines(result.judge))
        steps = ", ".join(f"{step} {seconds:.0f}s" for step, seconds in result.seconds.items())
        print(f"round {result.number}: {steps}; {len(result.report.findings)} verify findings, "
              f"{len(result.judge)} judge findings", flush=True)

    started = time.monotonic()
    done = await unbrand_document(pdf, brief, editor=PyMuPdfEditor(),
                                  inspector=PyMuPdfInspector(), models=models,
                                  max_rounds=args.max_rounds, on_round=save_round)
    seconds = time.monotonic() - started

    kept = [page for page in range(1, pages + 1) if page not in done.dropped_pages]
    damage = [finding for finding in done.report.findings if finding.check is Check.DAMAGE]
    run = {
        "pages": pages, "rounds": done.rounds, "seconds": round(seconds),
        "plan_seconds": round(done.plan_seconds), "dropped_pages": done.dropped_pages,
        "kept_pages": kept, "passed": done.report.passed,
        "sorting": [page.model_dump() for page in done.sorting.pages],
        "terms": done.sorting.terms,
        "damage": {severity.value: sum(finding.severity is severity for finding in damage)
                   for severity in Severity},
        "judge_findings": len(done.judge),
        "models": {"sort": args.sort_model, "pick": args.pick_model,
                   "judge": args.judge_model, "repair": args.repair_model},
        "thinking": thinking,
        "usage": {role: usage.model_dump() for role, usage in models.usage.items()},
        "dropped_steps": models.dropped,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2))

    for outcome in done.outcomes:
        mark = "ok " if outcome.ok else "NO "
        print(f"{mark} {outcome.action.model_dump(exclude={'why'})}  {outcome.detail}".rstrip())
    for step in models.dropped:
        print(f"dropped step: {step}")
    print("\nverify:\n" + _lines(done.report.findings, indent="  "), end="")
    print("judge:\n" + _lines(done.judge, indent="  "), end="")
    cost = sum(usage.cost for usage in models.usage.values())
    tokens = sum(usage.input_tokens + usage.output_tokens for usage in models.usage.values())
    print("\nsorting:")
    for page in done.sorting.pages:
        print(f"  p{page.page:<3} {page.kind:14} {'keep' if page.keep else 'drop'}  {page.why}")
    if args.expect_pages is not None:
        extra = sorted(set(kept) - set(args.expect_pages))
        missing = sorted(set(args.expect_pages) - set(kept))
        print(f"kept pages: {'as expected' if not extra and not missing else ''}"
              f"{f' kept but not expected {extra}' if extra else ''}"
              f"{f' expected but dropped {missing}' if missing else ''}")
    print(f"\n{'PASS' if done.report.passed else 'FAIL'}: {pages} pages, {done.rounds} rounds, "
          f"{len(done.actions)} actions, {tokens} tokens, ${cost:.4f}, {seconds:.0f}s "
          f"(plan {done.plan_seconds:.0f}s)")
    print(f"output: {out.relative_to(ROOT)}")
    return 0 if done.report.passed and not done.judge else 1


def _page_list(text: str) -> list[int]:
    """"8-12,15-22" as [8, 9, ..., 22]."""
    out: list[int] = []
    for part in text.split(","):
        first, _, last = part.partition("-")
        out += range(int(first), int(last or first) + 1)
    return out


def _lines(findings: list[Finding], indent: str = "") -> str:
    return "".join(f"{indent}{_line(finding)}\n" for finding in findings)


def _line(finding: Finding) -> str:
    where = f"p{finding.page}" if finding.page else "doc"
    return f"{finding.severity.value:5}  {finding.check.value:10}  {where:4}  {finding.detail}"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
