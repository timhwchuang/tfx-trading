"""CLI: run tick replay backtest (delegates to trading-backtest)."""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

from config import LOG_FILE, LOG_LEVEL, PRODUCT_CODE
from storage.cache_paths import DEFAULT_REPORTS_DIR, DEFAULT_TICK_CACHE_DIR
from storage.tick_loader import DEFAULT_CACHE_DIR, resolve_cli_tick_cache_dates
from trading_engine.logging_setup import (
    flush_async_logging,
    setup_async_logging,
    shutdown_async_logging,
)

# App-wired BacktestEngine (trading-app ports + default strategy)
from .engine import BacktestEngine


def _date_range_tag(dates: list[datetime.date]) -> str:
    if len(dates) == 1:
        return dates[0].strftime("%Y%m%d")
    return f"{dates[0].strftime('%Y%m%d')}_{dates[-1].strftime('%Y%m%d')}"


def default_log_path(code: str, dates: list[datetime.date]) -> Path:
    logs_dir = DEFAULT_TICK_CACHE_DIR.parent / "logs"
    return logs_dir / f"backtest_{code}_{_date_range_tag(dates)}.log"


def default_report_json_path(code: str, dates: list[datetime.date]) -> Path:
    return DEFAULT_REPORTS_DIR / f"backtest_{code}_{_date_range_tag(dates)}.json"


def configure_backtest_session_logging(
    log_file: str | None,
    *,
    console_level: str | None = None,
    truncate: bool = False,
) -> None:
    """Async logging for one backtest run (same sink as live via setup_async_logging).

    When ``truncate`` is true, delete ``log_file`` first (fresh UTF-8 log per run).
    Must run before ``BacktestEngine`` when ``log_file`` is set so ``_ensure_logging()`` is a no-op.
    """
    from integrations import engine_wiring

    shutdown_async_logging()
    engine_wiring._logging_configured = False

    path = (log_file or "").strip()
    if path and truncate:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)

    setup_async_logging(
        level=LOG_LEVEL,
        log_file=path,
        console_level=console_level,
    )
    engine_wiring._logging_configured = bool(path)


def _safe_print(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass
    print(text, flush=True)


def emit_report(
    log_path: Path,
    *,
    print_report: bool,
    json_path: Path | None,
) -> None:
    from reporting.uat_report import compute_metrics, format_report, read_log_lines

    flush_async_logging()
    lines = read_log_lines([log_path])
    if not lines:
        logging.warning(
            "Backtest log is empty: %s (no audit lines captured this run)",
            log_path,
        )
    metrics = compute_metrics(lines)
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logging.info("Wrote report JSON → %s", json_path)
    if print_report:
        _safe_print("\n" + format_report(metrics))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run VWAP momentum backtest (app-wired BacktestEngine).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m backtest --dates 2026-06-12\n"
            "  python -m backtest --dates 2026-06-22 --report\n"
            "  python -m backtest --dates 2026-06-22 --report-json\n"
            "  python -m backtest --dates-from-cache --report "
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
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "UTF-8 backtest log via async logging (overwrite each run). "
            "Default logs/backtest_{code}_{date}.log when --report/--report-json; "
            "otherwise uses config LOG_FILE when set."
        ),
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print UAT report after run (also enabled by --report-json)",
    )
    parser.add_argument(
        "--report-json",
        nargs="?",
        const="__default__",
        default=None,
        metavar="PATH",
        help=(
            "Write metrics JSON and print UAT report "
            "(default path: reports/backtest_{code}_{date}.json)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    want_report = args.report or args.report_json is not None
    log_path = args.log_file

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
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.error("%s", exc)
        return 1

    if log_path is None and want_report:
        log_path = default_log_path(args.code, dates)

    session_log: str | None = None
    truncate_log = False
    console_level: str | None = None
    if log_path is not None:
        session_log = str(log_path)
        truncate_log = True
        console_level = "OFF" if want_report else None
    elif LOG_FILE:
        session_log = LOG_FILE

    if session_log is not None:
        configure_backtest_session_logging(
            session_log,
            console_level=console_level,
            truncate=truncate_log,
        )

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

    if want_report:
        assert log_path is not None
        json_path: Path | None = None
        if args.report_json is not None:
            json_path = (
                default_report_json_path(args.code, dates)
                if args.report_json == "__default__"
                else Path(args.report_json)
            )
        emit_report(log_path, print_report=True, json_path=json_path)

    if log_path is not None:
        logging.info("Backtest log → %s", log_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
