"""Phase 4: Determinism gate — SHA-256 over canonical audit JSON lines."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Iterable, List

from backtest.engine import BacktestEngine
from config import PRODUCT_CODE
from core.runtime_config import default_runtime_config
from integrations.engine_wiring import build_strategy_session
from observability import DailyObservability
from storage.tick_loader import DEFAULT_CACHE_DIR

_AUDIT_PREFIXES = ("SIGNAL_AUDIT ", "FILL_AUDIT ", "DAILY_SUMMARY ", "DECISION_AUDIT ", "EXEC_AUDIT ")
# FT-001 Phase 4: DECISION_AUDIT and EXEC_AUDIT included for full audit contract determinism.
_NON_DETERMINISTIC_OPERATIONAL_KEYS = frozenset(
    {
        "lock_wait_max_ms",
        "lock_wait_over_50ms",
        "no_tick_resubscribe",
        "atr_min",
        "atr_max",
        "atr_samples",
        "tick_type",
    }
)
_AUDIT_LOGGERS = (
    "trading_engine",
    "strategy_vwap_momentum",
    "strategy_gudt_route_a",
)


def normalize_audit_for_hash(label: str, json_part: str) -> str:
    """Canonical JSON for hashing; strips wall-clock / ops telemetry from DAILY_SUMMARY."""
    obj = json.loads(json_part)
    if label == "DAILY_SUMMARY":
        operational = obj.get("operational")
        if isinstance(operational, dict):
            obj = {
                **obj,
                "operational": {
                    k: v
                    for k, v in operational.items()
                    if k not in _NON_DETERMINISTIC_OPERATIONAL_KEYS
                },
            }
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_audit_json(json_part: str) -> str:
    """Parse and re-serialize with stable key order (6.8)."""
    obj = json.loads(json_part)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class _AuditCaptureHandler(logging.Handler):
    def __init__(self, *, prefixes: tuple[str, ...] = _AUDIT_PREFIXES) -> None:
        super().__init__()
        self._prefixes = prefixes
        self.records: List[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        for prefix in self._prefixes:
            if msg.startswith(prefix):
                label = prefix.strip()
                self.records.append((label, msg[len(prefix) :]))
                return


def _run_with_audit_capture(
    fn,
    *,
    capture_prefixes: tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    prefixes = capture_prefixes if capture_prefixes is not None else _AUDIT_PREFIXES
    handler = _AuditCaptureHandler(prefixes=prefixes)
    loggers: list[tuple[logging.Logger, int]] = []
    for name in _AUDIT_LOGGERS:
        logger = logging.getLogger(name)
        loggers.append((logger, logger.level))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        fn()
    finally:
        for logger, prev_level in loggers:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
    return handler.records


def hash_audit_records(records: Iterable[tuple[str, str]]) -> str:
    hasher = hashlib.sha256()
    for label, json_part in records:
        hasher.update(normalize_audit_for_hash(label, json_part).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def hash_audit_lines(json_parts: Iterable[str]) -> str:
    """Hash raw JSON payloads (no DAILY_SUMMARY operational stripping)."""
    hasher = hashlib.sha256()
    for json_part in json_parts:
        hasher.update(canonical_audit_json(json_part).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def run_hash(
    code: str,
    dates: list[datetime.date],
    cache_dir=DEFAULT_CACHE_DIR,
) -> str:
    """Run one backtest and hash SIGNAL_AUDIT + FILL_AUDIT + DAILY_SUMMARY JSON."""

    def _run() -> None:
        cfg = default_runtime_config()
        obs = DailyObservability()
        strategy = build_strategy_session(
            cfg,
            obs,
            code=code,
            dates=dates,
            cache_dir=Path(cache_dir),
            mode="backtest",
        )
        engine = BacktestEngine(
            code,
            dates,
            cache_dir=Path(cache_dir),
            strategy=strategy,
            runtime_config=cfg,
            obs=obs,
        )
        engine.run()

    records = _run_with_audit_capture(_run)
    return hash_audit_records(records)


def capture_backtest_log_lines(
    code: str,
    dates: list[datetime.date],
    cache_dir=DEFAULT_CACHE_DIR,
) -> list[str]:
    """Return uat_report-compatible log lines from a backtest run."""

    def _run() -> None:
        cfg = default_runtime_config()
        obs = DailyObservability()
        strategy = build_strategy_session(
            cfg,
            obs,
            code=code,
            dates=dates,
            cache_dir=Path(cache_dir),
            mode="backtest",
        )
        engine = BacktestEngine(
            code,
            dates,
            cache_dir=Path(cache_dir),
            strategy=strategy,
            runtime_config=cfg,
            obs=obs,
        )
        engine.run()

    records = _run_with_audit_capture(_run)
    return [f"10:00:00 [INFO] {label} {payload}" for label, payload in records]


def build_parser() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(
        description="Determinism check helper for UAT (backtest audit hash).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m sweep.determinism_check --date 2026-06-12 --mode hash\n"
            "  python -m sweep.determinism_check --date 2026-06-12 --mode hash "
            "--output ..\\..\\..\\snapshots\\determinism_20260612.txt\n"
            "  python -m sweep.determinism_check --date 2026-06-12 --mode capture --output audits.log\n"
        ),
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Date in YYYY-MM-DD for backtest (or use for log capture)",
    )
    parser.add_argument(
        "--code",
        default=PRODUCT_CODE,
        help=f"Contract code (default: config product_code={PRODUCT_CODE})",
    )
    parser.add_argument("--output", help="Optional path to write hash or lines")
    parser.add_argument(
        "--mode",
        choices=["hash", "capture"],
        default="hash",
        help="Run backtest and hash, or just capture lines",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    dates = [datetime.date.fromisoformat(args.date)]
    if args.mode == "hash":
        h = run_hash(args.code, dates)
        print(f"Determinism hash for {args.date}: {h}")
        if args.output:
            Path(args.output).write_text(h)
    else:
        lines = capture_backtest_log_lines(args.code, dates)
        if args.output:
            Path(args.output).write_text("\n".join(lines))
        else:
            for line in lines:
                print(line)


if __name__ == "__main__":
    main()