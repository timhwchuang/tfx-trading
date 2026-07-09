"""CLI: backfill historical ticks/kbars via Shioaji into monorepo cache dirs."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import PRODUCT_CODE
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR

from backfilldata.core import (
    BackfillError,
    backfill_dates_batched,
    backfill_month,
    filter_backfill_eligible_dates,
    parse_date_args,
    parse_month_arg,
)

_EPILOG = """\
Examples (from apps/trading-app/src):
  python -m backfilldata date 2026-06-20
  python -m backfilldata date 2026-07-01 2026-07-06
  python -m backfilldata month 2026-04
  python -m backfilldata month 2026-04 --dry-run
  python -m backfilldata date 2026-06-20 --code TMFR1 --production

Environment:
  SJ_API_KEY, SJ_SEC_KEY     Shioaji credentials (market data only; no CA)
  CONFIG_PATH                optional config.yaml (product_code)

Cache layout (defaults):
  ticks  → <monorepo>/tick_cache/{code}_{date}.csv   (calendar day D only)
  kbars  → <monorepo>/tick_cache/{code}_kbars_{date}.csv

Notes:
  Module name is backfilldata (not backfilldate).
  date/month iterate every calendar day (no holiday filter); empty days skip write.
  Always AllDay ticks+kbars; automatic rollover merge stays on.
  Prefer after day session close (13:45 Taipei). Default API mode is UAT (--uat).
  See backfilldata/SPEC.md for API limits.
"""


def _resolve_simulation(args: argparse.Namespace) -> bool:
    if args.production:
        return False
    return True


def _add_backfill_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--code",
        default=PRODUCT_CODE,
        help=f"Continuous futures code (default: config product_code={PRODUCT_CODE})",
    )
    parser.add_argument(
        "--tick-cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        help="Directory for tick and kbar CSV cache",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even when cache file exists",
    )
    api_mode = parser.add_mutually_exclusive_group()
    api_mode.add_argument(
        "--uat",
        action="store_true",
        help="Shioaji simulation API (default when neither --uat nor --production)",
    )
    api_mode.add_argument(
        "--production",
        action="store_true",
        help="Shioaji production API",
    )


def _backfill_kwargs(args: argparse.Namespace, *, simulation: bool) -> dict:
    return {
        "code": args.code,
        "simulation": simulation,
        "fetch_ticks": True,
        "fetch_kbars": True,
        "cache_dir": Path(args.tick_cache_dir),
        "overwrite": args.overwrite,
        "tick_time_start": None,
        "tick_time_end": None,
        "merge_rollover": True,
    }


def _report_backfill_result(
    result,
    *,
    dates: list,
    simulation: bool,
) -> int:
    if not result.ok:
        logging.error(
            "API failures: %s",
            ", ".join(d.isoformat() for d in result.failed_dates),
        )
        return 1

    logging.info(
        "完成 | dates=%d tick_files=%d kbar_paths=%d simulation=%s",
        len(dates),
        len(result.ticks),
        len(result.kbars),
        simulation,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill Shioaji historical ticks and 1m kbars into local CSV cache.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    date_p = sub.add_parser(
        "date",
        help="Backfill every calendar day in one date or inclusive start end range",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    date_p.add_argument(
        "dates",
        nargs="+",
        metavar="YYYY-MM-DD",
        help="One date, or start and end (inclusive); every calendar day is attempted",
    )
    _add_backfill_options(date_p)

    month_p = sub.add_parser(
        "month",
        help="Backfill every calendar day in a month (empty days OK)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    month_p.add_argument(
        "month",
        metavar="YYYY-MM",
        help="Calendar month (e.g. 2026-04)",
    )
    month_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print eligible calendar days only; do not call Shioaji",
    )
    _add_backfill_options(month_p)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    simulation = _resolve_simulation(args)
    kwargs = _backfill_kwargs(args, simulation=simulation)

    try:
        if args.command == "date":
            raw_dates = parse_date_args(args.dates)
            eligible, skipped_future = filter_backfill_eligible_dates(raw_dates)
            logging.info(
                "date | requested=%d eligible=%d skipped_future=%d",
                len(raw_dates),
                len(eligible),
                len(skipped_future),
            )
            if not eligible:
                logging.info("無可 backfill 的日期")
                return 0
            result, batches = backfill_dates_batched(
                eligible,
                range_start=raw_dates[0],
                range_end=raw_dates[-1],
                **kwargs,
            )
            logging.info(
                "date | eligible=%d batches=%d",
                len(eligible),
                len(batches),
            )
            return _report_backfill_result(
                result,
                dates=eligible,
                simulation=simulation,
            )

        year, month = parse_month_arg(args.month)

        if args.dry_run:
            from backfilldata.core import calendar_days_in_month

            calendar_days = calendar_days_in_month(year, month)
            eligible, skipped_future = filter_backfill_eligible_dates(calendar_days)
            logging.info(
                "dry-run | month=%04d-%02d calendar_days=%d eligible=%d skipped_future=%d",
                year,
                month,
                len(calendar_days),
                len(eligible),
                len(skipped_future),
            )
            for d in eligible:
                logging.info("  backfill %s", d.isoformat())
            return 0

        result, meta = backfill_month(year, month, **kwargs)
        logging.info(
            "month=%04d-%02d | calendar_days=%d eligible=%d batches=%d skipped_future=%d",
            year,
            month,
            len(meta["calendar_days"]),
            len(meta["eligible_days"]),
            len(meta["batches"]),
            len(meta["skipped_future"]),
        )
        return _report_backfill_result(
            result,
            dates=meta["eligible_days"],
            simulation=simulation,
        )
    except BackfillError as e:
        print(f"backfilldata: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logging.exception("backfilldata 未預期錯誤")
        print(f"backfilldata: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
