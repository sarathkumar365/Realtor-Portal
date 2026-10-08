"""Run verify() on a real source PDF and its cleaned version, by hand.

Not a pytest: real builder PDFs stay out of git (.local/). Prints every finding
and exits 1 unless the document passes.

    .venv/bin/python scripts/unbrand_verify.py source.pdf cleaned.pdf \\
        --builder "Arista Homes" --project SouthCal [--short AH] [--dropped 3 --dropped 7]
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.domain import HitList
from app.capabilities.unbrander.verify import verify


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("cleaned")
    parser.add_argument("--builder", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--short", action="append", default=[])
    parser.add_argument("--extra", action="append", default=[])
    parser.add_argument("--dropped", action="append", type=int)
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR; the report then blocks")
    args = parser.parse_args()

    inspector = PyMuPdfInspector()
    started = time.monotonic()
    source = inspector.inspect(Path(args.source).read_bytes(), ocr=False)
    cleaned = inspector.inspect(Path(args.cleaned).read_bytes(), ocr=not args.no_ocr)
    hits = HitList(builder=args.builder, project=args.project,
                   short_forms=args.short, extras=args.extra)
    report = verify(source, cleaned, hits, dropped_pages=args.dropped)

    for finding in report.findings:
        where = f"p{finding.page}" if finding.page else "doc"
        print(f"{finding.severity.value:5}  {finding.check.value:10}  {where:4}  "
              f"{finding.detail}")
    seconds = time.monotonic() - started
    print(f"\n{'PASS' if report.passed else 'FAIL'}: {len(report.findings)} findings, "
          f"{len(cleaned.pages)} pages, {seconds:.0f}s")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
