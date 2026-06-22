"""CLI: backfill historical ticks/kbars via Shioaji into monorepo cache dirs."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import PRODUCT_CODE, SIMULATION
from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR, DEFAULT_TICK_CACHE_DIR

from backfilldata.core import BackfillError, backfill_dates, parse_date_args

_EPILOG = """\
Examples (from apps/trading-app/src):
  python -m backfilldata date 2026-06-20
  python -m backfilldata date 2026-06-18 2026-06-20
  python -m backfilldata date 2026-06-20 --code TMFR1 --ticks-only
  python -m backfilldata date 2026-06-20 --kbars-only --no-mirror-kbars

Environment:
  SJ_API_KEY, SJ_SEC_KEY     Shioaji credentials (market data only; no CA)
  CONFIG_PATH                optional config.yaml (product_code, simulation)

Cache layout (defaults):
  ticks  → <monorepo>/tick_cache/{code}_{date}.csv
  kbars  → <monorepo>/kbar_cache/{code}_kbars_{date}.csv
           (+ mirror to tick_cache when --mirror-kbars, matching UAT archiver)

Notes:
  Prefer running after market close; Shioaji intraday limits: ticks 10/day, kbars 270/day.
  Do not run while live session holds one of the 5 connection slots for the same person_id.
  See backfilldata/SPEC.md for API limits and fidelity caveats.
"""


def _resolve_simulation(args: argparse.Namespace) -> bool:
    if args.production:
        return False
    if args.simulation:
        return True
    return SIMULATION


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
    date_p.add_argument(
        "--code",
        default=PRODUCT_CODE,
        help=f"Continuous futures code (default: config product_code={PRODUCT_CODE})",
    )
    date_p.add_argument(
        "--tick-cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        help="Directory for tick CSV cache",
    )
    date_p.add_argument(
        "--kbar-cache-dir",
        type=Path,
        default=DEFAULT_KBAR_CACHE_DIR,
        help="Primary directory for kbar CSV cache (sweep / calibration consumers)",
    )
    date_p.add_argument(
        "--ticks-only",
        action="store_true",
        help="Fetch ticks only",
    )
    date_p.add_argument(
        "--kbars-only",
        action="store_true",
        help="Fetch kbars only",
    )
    date_p.add_argument(
        "--mirror-kbars",
        dest="mirror_kbars",
        action="store_true",
        default=True,
        help="Also write kbars under tick_cache (UAT archiver layout; default on)",
    )
    date_p.add_argument(
        "--no-mirror-kbars",
        dest="mirror_kbars",
        action="store_false",
        help="Keep kbars only under kbar_cache",
    )
    date_p.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even when cache file exists",
    )
    api_mode = date_p.add_mutually_exclusive_group()
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.ticks_only and args.kbars_only:
        print("不可同時指定 --ticks-only 與 --kbars-only", file=sys.stderr)
        return 2

    simulation = _resolve_simulation(args)

    try:
        dates = parse_date_args(args.dates)
        result = backfill_dates(
            dates,
            code=args.code,
            simulation=simulation,
            fetch_ticks=not args.kbars_only,
            fetch_kbars=not args.ticks_only,
            tick_cache_dir=Path(args.tick_cache_dir),
            kbar_cache_dir=Path(args.kbar_cache_dir),
            mirror_kbars_to_tick_cache=args.mirror_kbars,
            overwrite=args.overwrite,
        )
    except BackfillError as e:
        print(f"backfilldata: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logging.exception("backfilldata 未預期錯誤")
        print(f"backfilldata: {e}", file=sys.stderr)
        return 1

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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
