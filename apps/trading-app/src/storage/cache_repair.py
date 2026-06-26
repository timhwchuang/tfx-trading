"""Batch repair tick_cache: rollover afternoon merge + kbar gap fill from ticks."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from storage.cache_audit import (
    DayAuditReport,
    audit_day,
    discover_tick_cache_pairs,
    format_day_line,
    format_day_report,
    format_scan_summary,
    scan_cache_dir,
)
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_repair import repair_kbars_batch, repair_kbars_from_ticks
from storage.tick_loader import load_merged_tick_cache
from storage.tick_rollover import (
    merge_rollover_afternoon_batch,
    ticks_need_rollover_afternoon,
)

logger = logging.getLogger(__name__)

_REQUEST_PACE_SEC = 0.15


@dataclass
class RepairResult:
    rollover_dates: list[datetime.date] = field(default_factory=list)
    kbar_dates: list[tuple[datetime.date, int]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def repair_cache(
    code: str,
    dates: list[datetime.date],
    *,
    cache_dir: Path,
    fetch_rollover: bool,
    fix_kbars: bool,
    api: object | None = None,
    simulation: bool = True,
    resolve_contract: object | None = None,
) -> RepairResult:
    """Repair rollover tick tails (API) and kbar gaps (from ticks)."""
    result = RepairResult()

    if fetch_rollover:
        rollover_candidates = [
            d
            for d in dates
            if ticks_need_rollover_afternoon(
                load_merged_tick_cache(cache_dir, code, d),
                d,
            )
        ]
        if rollover_candidates:
            if api is None or resolve_contract is None:
                from backfilldata.core import create_and_login_api, resolve_contract as _rc

                api = create_and_login_api(simulation=simulation)
                resolve_contract = _rc
                owns_api = True
            else:
                owns_api = False
            try:
                result.rollover_dates = merge_rollover_afternoon_batch(
                    api,
                    code,
                    rollover_candidates,
                    cache_dir=cache_dir,
                    simulation=simulation,
                    resolve_contract=resolve_contract,
                )
                time.sleep(_REQUEST_PACE_SEC)
            finally:
                if owns_api and api is not None:
                    try:
                        api.logout()
                    except Exception as e:
                        logger.warning("api.logout 失敗: %s", e)

    if fix_kbars:
        result.kbar_dates = repair_kbars_batch(
            code,
            dates,
            cache_dir=cache_dir,
            rollover_dates=(
                set(result.rollover_dates) if result.rollover_dates else None
            ),
        )

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Repair tick_cache: merge TMFR1+TMFR2 afternoon ticks, "
            "fill missing kbars from ticks, then audit."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples (from apps/trading-app/src):
  # 掃描（不修改）
  python -m storage.cache_repair --code TMFR1 --audit-only

  # 補跨月15分鐘 + kbar缺口 + 重比對
  source ~/sinotrade/uat-env.sh
  python -m storage.cache_repair --code TMFR1 --fix

  # 只從本地 ticks 補 kbar（不呼叫 API）
  python -m storage.cache_repair --code TMFR1 --fix-kbars-only
""",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_TICK_CACHE_DIR,
        help="tick_cache root (ticks and kbars)",
    )
    parser.add_argument("--code", default="TMFR1", help="Contract code (default TMFR1)")
    parser.add_argument("--date", type=datetime.date.fromisoformat, help="Single day")
    parser.add_argument("--from-date", type=datetime.date.fromisoformat, dest="from_date")
    parser.add_argument("--to-date", type=datetime.date.fromisoformat, dest="to_date")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--audit-only",
        action="store_true",
        help="Scan only, no file changes (default without --fix)",
    )
    mode.add_argument(
        "--fix",
        action="store_true",
        help="Fetch rollover ticks (API) + fill kbar gaps from ticks",
    )
    mode.add_argument(
        "--fix-kbars-only",
        action="store_true",
        help="Fill kbar gaps from ticks only (no API)",
    )
    parser.add_argument(
        "--simulation",
        action="store_true",
        default=None,
        help="Use Shioaji simulation API (default: config.yaml)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use production API",
    )
    parser.add_argument(
        "--vol-warn-threshold",
        type=int,
        default=20,
        help="Summary threshold for high vol-diff days",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _resolve_simulation(args: argparse.Namespace) -> bool:
    if args.production:
        return False
    if args.simulation:
        return True
    try:
        import config as app_config

        return bool(app_config.SIMULATION)
    except Exception:
        return True


def _resolve_dates(args: argparse.Namespace, cache_dir: Path) -> list[datetime.date]:
    if args.date is not None:
        return [args.date]
    return [
        d
        for c, d in discover_tick_cache_pairs(
            cache_dir,
            code=args.code,
            start=args.from_date,
            end=args.to_date,
        )
        if c == args.code
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    cache_dir = Path(args.cache_dir)
    dates = _resolve_dates(args, cache_dir)
    if not dates:
        print(f"cache_repair: 無 {args.code} tick 快取", file=sys.stderr)
        return 1

    do_fix = args.fix or args.fix_kbars_only
    fetch_rollover = args.fix and not args.fix_kbars_only

    if do_fix and not args.audit_only:
        print(f"=== 修復 {args.code} | {len(dates)} 天 ===")
        repair = repair_cache(
            args.code,
            dates,
            cache_dir=cache_dir,
            fetch_rollover=fetch_rollover,
            fix_kbars=True,
            simulation=_resolve_simulation(args),
        )
        if repair.rollover_dates:
            print(
                f"跨月 tick 合併: {len(repair.rollover_dates)} 天 — "
                + ", ".join(d.isoformat() for d in repair.rollover_dates)
            )
        if repair.kbar_dates:
            print(
                f"kbar 補洞: {len(repair.kbar_dates)} 天 — "
                + ", ".join(f"{d}(+{n})" for d, n in repair.kbar_dates)
            )
        if not repair.rollover_dates and not repair.kbar_dates:
            print("無需修復的項目")
        print()

    print(f"=== 稽核 {args.code} | {len(dates)} 天 ===")
    reports: list[DayAuditReport] = []
    for d in dates:
        report = audit_day(
            args.code,
            d,
            cache_dir=cache_dir,
            max_examples=3,
        )
        reports.append(report)
        print(format_day_line(report))
        if args.verbose and report.severity != "OK":
            print(format_day_report(report, verbose=True).split("\n", 1)[-1])

    print()
    print(format_scan_summary(reports, vol_warn_threshold=args.vol_warn_threshold))
    return 0 if not any(r.severity == "FAIL" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
