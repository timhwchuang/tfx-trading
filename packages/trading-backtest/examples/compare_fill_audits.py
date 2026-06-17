#!/usr/bin/env python3
"""Compare FILL_AUDIT statistics between a backtest log and a paper/live reference log.

Usage:
    python examples/compare_fill_audits.py backtest.log paper.log

Both files should contain standard trading_engine log lines with FILL_AUDIT JSON payloads.
See SPEC.md §9 for the recommended validation pipeline.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import sys
from pathlib import Path

from trading_backtest.validation import (
    compare_fill_audits,
    format_fill_comparison,
    parse_fill_audits_from_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backtest_log", type=Path, help="Log file from backtest run")
    parser.add_argument("reference_log", type=Path, help="Log file from paper or live run")
    args = parser.parse_args(argv)

    if not args.backtest_log.is_file():
        print(f"error: not found: {args.backtest_log}", file=sys.stderr)
        return 2
    if not args.reference_log.is_file():
        print(f"error: not found: {args.reference_log}", file=sys.stderr)
        return 2

    bt_fills = parse_fill_audits_from_file(args.backtest_log)
    ref_fills = parse_fill_audits_from_file(args.reference_log)
    report = compare_fill_audits(bt_fills, ref_fills)
    print(format_fill_comparison(report))
    return 1 if report.warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())