"""CLI: run tick replay backtest (delegates to trading-backtest)."""

from __future__ import annotations

import argparse
import logging

from config import PRODUCT_CODE
from storage.tick_loader import DEFAULT_CACHE_DIR, resolve_cli_tick_cache_dates

# App-wired BacktestEngine (trading-app ports + default strategy)
from .engine import BacktestEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run VWAP momentum backtest (app-wired BacktestEngine).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m backtest --dates 2026-06-12\n"
            "  python -m backtest --dates 2026-06-12 2026-06-13\n"
            "  python -m backtest --dates-from-cache\n"
            "  python -m backtest --dates-from-cache "
            "--from-date 2026-06-01 --to-date 2026-06-30\n"
        ),
    )
    parser.add_argument(
        "--code",
        default=PRODUCT_CODE,
        help=f"Futures product code (default: config product_code={PRODUCT_CODE})",
    )
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--dates",
        nargs="+",
        help="Trade dates YYYY-MM-DD",
    )
    date_group.add_argument(
        "--dates-from-cache",
        action="store_true",
        help="Use all tick_cache dates for --code (optional --from-date/--to-date)",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default="",
        help="With --dates-from-cache: inclusive min date YYYY-MM-DD",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default="",
        help="With --dates-from-cache: inclusive max date YYYY-MM-DD",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=str(DEFAULT_CACHE_DIR),
        help="Tick cache directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        dates = resolve_cli_tick_cache_dates(
            explicit=args.dates,
            from_cache=args.dates_from_cache,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    except ValueError as exc:
        logging.error("%s", exc)
        return 1

    if args.dates_from_cache:
        logging.info(
            "dates-from-cache | code=%s count=%d range=%s..%s",
            args.code,
            len(dates),
            dates[0].isoformat(),
            dates[-1].isoformat(),
        )

    engine = BacktestEngine(args.code, dates, cache_dir=args.cache_dir)
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
