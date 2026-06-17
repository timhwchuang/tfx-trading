#!/usr/bin/env python3
"""Write a minimal valid tick-cache CSV template for local testing.

Usage:
    python examples/tick_cache_template.py --code TXFR1 --date 2026-06-12 --output tick_cache/

Produces `{output}/{code}_{date}.csv` with a short synthetic session snippet.
Replace with your own recorded ticks for real backtests.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import csv
import datetime
from pathlib import Path

from trading_backtest.loader import TICK_CSV_FIELDS, cache_path


def _synthetic_rows(day: datetime.date) -> list[dict[str, str]]:
    base = datetime.datetime.combine(day, datetime.time(8, 45))
    prices = [17990.0, 17995.0, 18000.0, 18001.0, 18002.0]
    rows: list[dict[str, str]] = []
    for i, price in enumerate(prices):
        ts = base + datetime.timedelta(seconds=i)
        rows.append(
            {
                "datetime": ts.isoformat(),
                "close": f"{price:.1f}",
                "volume": str(1 + i % 3),
                "bid_price": f"{price - 1:.1f}",
                "ask_price": f"{price + 1:.1f}",
                "tick_type": str(i % 3),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", default="TXFR1")
    parser.add_argument("--date", type=datetime.date.fromisoformat, default="2026-06-12")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tick_cache"),
        help="Cache directory (default: ./tick_cache)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(out_dir, args.code, args.date)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TICK_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_synthetic_rows(args.date))

    print(f"wrote {path}")
    print("Replace synthetic ticks with your recorded data before serious validation.")


if __name__ == "__main__":
    main()