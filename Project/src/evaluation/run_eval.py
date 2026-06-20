"""Command-line entry point for the evaluation harness (US-16).

Usage:
    python -m src.evaluation.run_eval [--k 5] [--strict] [--max-events 200]
                                      [--gold PATH] [--out DIR]

Runs the gold benchmark through the pipeline, writes a JSON + Markdown report to
``outputs/evaluation/``, and prints the aggregate metrics. With ``--strict`` the
process exits non-zero when any scored metric falls outside its threshold.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.evaluation.harness import format_markdown, run_evaluation, write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the signal-intelligence gold benchmark.")
    parser.add_argument("--gold", type=Path, default=None, help="Path to gold_complaints.json.")
    parser.add_argument("--k", type=int, default=5, help="k for retrieval precision@k.")
    parser.add_argument("--max-events", type=int, default=None, help="Cap events loaded per product code.")
    parser.add_argument("--out", type=Path, default=None, help="Directory for the report files.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any scored metric fails its threshold.",
    )
    args = parser.parse_args(argv)

    report = run_evaluation(gold_path=args.gold, k=args.k, max_events_per_code=args.max_events)
    paths = write_report(report, out_dir=args.out)

    print(format_markdown(report))
    print(f"\nReport written to:\n  {paths['json']}\n  {paths['markdown']}")

    if args.strict and not report.passed:
        print("\nSTRICT mode: thresholds failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
