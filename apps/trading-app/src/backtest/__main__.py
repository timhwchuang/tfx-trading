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
from sweep.holdout_guard import assert_dates_unsealed
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


def _cache_dir_output_tag(cache_dir: str | Path) -> str:
    """Leaf name under monorepo ``tick_cache/``; ``{parent}_{leaf}`` elsewhere."""
    resolved = Path(cache_dir).resolve()
    try:
        resolved.relative_to(DEFAULT_TICK_CACHE_DIR.resolve())
    except ValueError:
        parent = resolved.parent.name
        if parent and parent != resolved.name:
            return f"{parent}_{resolved.name}"
    return resolved.name


def _cache_dir_report_tag(
    cache_dir: str | Path,
    dates: list[datetime.date],
    *,
    date_range_filtered: bool,
) -> str:
    tag = _cache_dir_output_tag(cache_dir)
    if date_range_filtered and dates:
        tag = f"{tag}_{_date_range_tag(dates)}"
    return tag


def default_log_path_for_dates(code: str, dates: list[datetime.date]) -> Path:
    logs_dir = DEFAULT_TICK_CACHE_DIR.parent / "logs"
    return logs_dir / f"backtest_{code}_{_date_range_tag(dates)}.log"


def default_report_json_path_for_dates(code: str, dates: list[datetime.date]) -> Path:
    return DEFAULT_REPORTS_DIR / f"backtest_{code}_{_date_range_tag(dates)}.json"


def default_log_path_for_cache_dir(
    cache_dir: str | Path,
    dates: list[datetime.date],
    *,
    date_range_filtered: bool,
) -> Path:
    tag = _cache_dir_report_tag(
        cache_dir, dates, date_range_filtered=date_range_filtered
    )
    logs_dir = DEFAULT_TICK_CACHE_DIR.parent / "logs"
    return logs_dir / f"backtest_{tag}.log"


def default_report_json_path_for_cache_dir(
    cache_dir: str | Path,
    dates: list[datetime.date],
    *,
    date_range_filtered: bool,
) -> Path:
    tag = _cache_dir_report_tag(
        cache_dir, dates, date_range_filtered=date_range_filtered
    )
    return DEFAULT_REPORTS_DIR / f"backtest_{tag}.json"


def report_json_path_for_log(log_path: Path) -> Path:
    """Pair JSON with a custom ``--log-file`` (same stem under ``reports/``)."""
    return DEFAULT_REPORTS_DIR / f"{log_path.stem}.json"


def default_report_paths(
    *,
    dates_from_cache: bool,
    code: str,
    dates: list[datetime.date],
    cache_dir: str | Path,
    date_range_filtered: bool = False,
) -> tuple[Path, Path]:
    if dates_from_cache:
        return (
            default_log_path_for_cache_dir(
                cache_dir, dates, date_range_filtered=date_range_filtered
            ),
            default_report_json_path_for_cache_dir(
                cache_dir, dates, date_range_filtered=date_range_filtered
            ),
        )
    return (
        default_log_path_for_dates(code, dates),
        default_report_json_path_for_dates(code, dates),
    )


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
            "  python -m backtest --dates-from-cache --report\n"
            "    -> logs/backtest_tick_cache.log + reports/backtest_tick_cache.json\n"
            "  python -m backtest --dates-from-cache --cache-dir tick_cache/2026_05 --report\n"
            "  python -m backtest --dates-from-cache --cache-dir tick_cache/2026_05 --report "
            "--from-date 2026-05-01 --to-date 2026-05-15\n"
            "    -> backtest_2026_05_20260501_20260515.*\n"
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
            "Override backtest log path (UTF-8, overwrite each run). "
            "With --report, JSON is reports/{log_stem}.json. "
            "Without --log-file, --report uses the computed logs/backtest_*.log path. "
            "Otherwise uses config LOG_FILE when set."
        ),
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help=(
            "After replay: print UAT report, write logs/backtest_*.log and "
            "reports/backtest_*.json. --dates -> backtest_{code}_{date}; "
            "--dates-from-cache -> backtest_{cache_dir_name} "
            "(+_{date_range} when --from-date/--to-date filter)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    want_report = args.report
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

    try:
        assert_dates_unsealed(dates)
    except RuntimeError as exc:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.error("%s", exc)
        return 1

    date_range_filtered = args.dates_from_cache and bool(
        args.from_date or args.to_date
    )
    default_log, default_json = default_report_paths(
        dates_from_cache=args.dates_from_cache,
        code=args.code,
        dates=dates,
        cache_dir=args.cache_dir,
        date_range_filtered=date_range_filtered,
    )
    if log_path is None and want_report:
        log_path = default_log

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
        if log_path is None:
            logging.error("--report requires a backtest log path")
            return 1
        json_path = (
            report_json_path_for_log(log_path)
            if args.log_file is not None
            else default_json
        )
        emit_report(log_path, print_report=True, json_path=json_path)

    if log_path is not None:
        logging.info("Backtest log → %s", log_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
