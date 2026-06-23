"""CLI: backfill historical ticks/kbars via Shioaji into monorepo cache dirs."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path

from config import PRODUCT_CODE, SIMULATION
from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR, DEFAULT_TICK_CACHE_DIR
from storage.tick_loader import DEFAULT_TICK_RANGE_END, DEFAULT_TICK_RANGE_START

from backfilldata.core import (
    BackfillError,
    backfill_dates,
    backfill_month,
    filter_backfill_eligible_dates,
    parse_date_args,
)
from backfilldata.taiwan_calendar import (
    parse_month_arg,
    resolve_month_trading_days_with_fallback,
)

_EPILOG = """\
Examples (from apps/trading-app/src):
  python -m backfilldata date 2026-06-20
  python -m backfilldata date 2026-06-18 2026-06-20
  python -m backfilldata month 2026-04
  python -m backfilldata month 2026-04 --dry-run
  python -m backfilldata date 2026-06-20 --code TMFR1 --ticks-only
  python -m backfilldata date 2026-06-20 --ticks-only --time-start 08:45 --time-end 13:45
  python -m backfilldata date 2026-06-20 --kbars-only --no-mirror-kbars
  python -m backfilldata date 2026-06-20 --all-day-ticks

Environment:
  SJ_API_KEY, SJ_SEC_KEY     Shioaji credentials (market data only; no CA)
  CONFIG_PATH                optional config.yaml (product_code, simulation)

Cache layout (defaults):
  ticks  → <monorepo>/tick_cache/{code}_{date}.csv
  kbars  → <monorepo>/kbar_cache/{code}_kbars_{date}.csv
           (+ mirror to tick_cache when --mirror-kbars, matching UAT archiver)

Notes:
  Prefer running after day session close (13:45 Taipei); same-day backfill is allowed from 13:45 onward.
  Tick backfill defaults to RangeTime 08:45:00-13:45:00; use --all-day-ticks to fetch the full day.
  month: skips weekends + pin-yi Taiwan calendar (fallback weekdays-only if API unreachable).
  Do not run while live session holds one of the 5 connection slots for the same person_id.
  See backfilldata/SPEC.md for API limits and fidelity caveats.
"""


def _resolve_simulation(args: argparse.Namespace) -> bool:
    if args.production:
        return False
    if args.simulation:
        return True
    return SIMULATION


def _parse_hhmmss(value: str) -> datetime.time:
    try:
        return datetime.time.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"無效時間格式: {value}（請用 HH:MM 或 HH:MM:SS）"
        ) from e


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
        help="Directory for tick CSV cache",
    )
    parser.add_argument(
        "--kbar-cache-dir",
        type=Path,
        default=DEFAULT_KBAR_CACHE_DIR,
        help="Primary directory for kbar CSV cache (sweep / calibration consumers)",
    )
    parser.add_argument(
        "--ticks-only",
        action="store_true",
        help="Fetch ticks only",
    )
    parser.add_argument(
        "--kbars-only",
        action="store_true",
        help="Fetch kbars only",
    )
    parser.add_argument(
        "--mirror-kbars",
        dest="mirror_kbars",
        action="store_true",
        default=True,
        help="Also write kbars under tick_cache (UAT archiver layout; default on)",
    )
    parser.add_argument(
        "--no-mirror-kbars",
        dest="mirror_kbars",
        action="store_false",
        help="Keep kbars only under kbar_cache",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even when cache file exists",
    )
    parser.add_argument(
        "--time-start",
        type=_parse_hhmmss,
        default=DEFAULT_TICK_RANGE_START,
        help="Session window start for ticks (RangeTime) and kbars post-filter (default: 08:45:00)",
    )
    parser.add_argument(
        "--time-end",
        type=_parse_hhmmss,
        default=DEFAULT_TICK_RANGE_END,
        help="Session window end for ticks (RangeTime) and kbars post-filter (default: 13:45:00)",
    )
    parser.add_argument(
        "--all-day-ticks",
        action="store_true",
        help="Use TicksQueryType.AllDay instead of RangeTime for ticks",
    )
    api_mode = parser.add_mutually_exclusive_group()
    api_mode.add_argument(
        "--simulation",
        action="store_true",
        help="Force Shioaji simulation API (default: config.yaml simulation)",
    )
    api_mode.add_argument(
        "--production",
        action="store_true",
        help="Force Shioaji production API (overrides config simulation)",
    )


def _validate_session_window(args: argparse.Namespace) -> int | None:
    if args.ticks_only and args.kbars_only:
        print("不可同時指定 --ticks-only 與 --kbars-only", file=sys.stderr)
        return 2
    if not args.all_day_ticks and args.time_end <= args.time_start:
        print("--time-end 必須晚於 --time-start", file=sys.stderr)
        return 2
    return None


def _backfill_kwargs(args: argparse.Namespace, *, simulation: bool) -> dict:
    tick_time_start = None if args.all_day_ticks else args.time_start
    tick_time_end = None if args.all_day_ticks else args.time_end
    return {
        "code": args.code,
        "simulation": simulation,
        "fetch_ticks": not args.kbars_only,
        "fetch_kbars": not args.ticks_only,
        "tick_cache_dir": Path(args.tick_cache_dir),
        "kbar_cache_dir": Path(args.kbar_cache_dir),
        "mirror_kbars_to_tick_cache": args.mirror_kbars,
        "overwrite": args.overwrite,
        "tick_time_start": tick_time_start,
        "tick_time_end": tick_time_end,
    }


def _resolve_month_days_with_calendar_fallback(
    year: int,
    month: int,
    *,
    use_holiday_calendar: bool,
) -> tuple[list[datetime.date], dict[str, list[datetime.date]]]:
    return resolve_month_trading_days_with_fallback(
        year,
        month,
        use_holiday_calendar=use_holiday_calendar,
    )


def _report_backfill_result(
    result,
    *,
    dates: list[datetime.date],
    simulation: bool,
) -> int:
    if not result.ok:
        if result.missing_tick_dates:
            logging.error(
                "tick 缺檔: %s",
                ", ".join(d.isoformat() for d in result.missing_tick_dates),
            )
        if result.missing_kbar_dates:
            logging.error(
                "kbar 缺檔: %s",
                ", ".join(d.isoformat() for d in result.missing_kbar_dates),
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
        description="Backfill Shioaji historical ticks and/or 1m kbars into local CSV cache.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    date_p = sub.add_parser(
        "date",
        help="Backfill one date or inclusive start end range",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    date_p.add_argument(
        "dates",
        nargs="+",
        metavar="YYYY-MM-DD",
        help="One date, or start and end (inclusive)",
    )
    _add_backfill_options(date_p)

    month_p = sub.add_parser(
        "month",
        help="Backfill trading weekdays in a calendar month (skip weekends/holidays)",
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
        help="Print trading days only; do not call Shioaji",
    )
    month_p.add_argument(
        "--no-holiday-calendar",
        action="store_true",
        help="Skip pin-yi Taiwan calendar API; use weekdays only",
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

    rc = _validate_session_window(args)
    if rc is not None:
        return rc

    simulation = _resolve_simulation(args)
    kwargs = _backfill_kwargs(args, simulation=simulation)

    try:
        if args.command == "date":
            dates = parse_date_args(args.dates)
            result = backfill_dates(dates, **kwargs)
            return _report_backfill_result(result, dates=dates, simulation=simulation)

        year, month = parse_month_arg(args.month)
        use_holiday_calendar = not args.no_holiday_calendar

        if args.dry_run:
            trading_days, skipped_buckets = _resolve_month_days_with_calendar_fallback(
                year,
                month,
                use_holiday_calendar=use_holiday_calendar,
            )
            eligible, skipped_future = filter_backfill_eligible_dates(trading_days)
            logging.info(
                "dry-run | month=%04d-%02d trading_days=%d eligible=%d "
                "skipped_weekend=%d skipped_holiday=%d skipped_future=%d",
                year,
                month,
                len(trading_days),
                len(eligible),
                len(skipped_buckets["weekend"]),
                len(skipped_buckets["holiday"]),
                len(skipped_future),
            )
            for d in eligible:
                logging.info("  backfill %s", d.isoformat())
            return 0

        result, meta = backfill_month(
            year,
            month,
            use_holiday_calendar=use_holiday_calendar,
            **kwargs,
        )

        logging.info(
            "month=%04d-%02d | trading_days=%d eligible=%d batches=%d "
            "skipped_weekend=%d skipped_holiday=%d skipped_future=%d",
            year,
            month,
            len(meta["trading_days"]),
            len(meta["eligible_days"]),
            len(meta["batches"]),
            len(meta["skipped_weekend"]),
            len(meta["skipped_holiday"]),
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