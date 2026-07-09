"""Audit log parsing, determinism hashing, and backtest-vs-reference fill comparison."""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AUDIT_PREFIXES = ("SIGNAL_AUDIT ", "FILL_AUDIT ", "DAILY_SUMMARY ")
FILL_AUDIT_LABEL = "FILL_AUDIT"

_NON_DETERMINISTIC_OPERATIONAL_KEYS = frozenset(
    {
        "lock_wait_max_ms",
        "lock_wait_over_50ms",
        "no_tick_resubscribe",
        "atr_min",
        "atr_max",
    }
)


def canonical_audit_json(json_part: str) -> str:
    """Parse and re-serialize with stable key order."""
    obj = json.loads(json_part)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_audit_for_hash(label: str, json_part: str) -> str:
    """Canonical JSON for hashing; strips non-deterministic DAILY_SUMMARY ops fields."""
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


def parse_audit_lines(text: str) -> list[tuple[str, str]]:
    """Extract (label, json_payload) audit records from log text."""
    records: list[tuple[str, str]] = []
    for line in text.splitlines():
        payload_start = line.find("FILL_AUDIT ")
        if payload_start < 0:
            payload_start = line.find("SIGNAL_AUDIT ")
        if payload_start < 0:
            payload_start = line.find("DAILY_SUMMARY ")
        if payload_start < 0:
            continue
        segment = line[payload_start:]
        for prefix in AUDIT_PREFIXES:
            if segment.startswith(prefix):
                label = prefix.strip()
                records.append((label, segment[len(prefix) :]))
                break
    return records


def parse_fill_audits(text: str) -> list[dict[str, Any]]:
    """Parse FILL_AUDIT JSON objects from log text."""
    fills: list[dict[str, Any]] = []
    for label, json_part in parse_audit_lines(text):
        if label != FILL_AUDIT_LABEL:
            continue
        fills.append(json.loads(json_part))
    return fills


def parse_fill_audits_from_file(path: Path | str) -> list[dict[str, Any]]:
    return parse_fill_audits(Path(path).read_text(encoding="utf-8"))


def slippage_vs_limit_pts(fill: dict[str, Any]) -> float | None:
    """Adverse slippage relative to limit (positive = worse fill)."""
    if "slippage_vs_limit_pts" in fill:
        return float(fill["slippage_vs_limit_pts"])
    fill_price = fill.get("fill_price")
    limit_price = fill.get("limit_price")
    direction = fill.get("direction")
    if fill_price is None or limit_price is None or direction not in ("Buy", "Sell"):
        return None
    fp = float(fill_price)
    lp = float(limit_price)
    if direction == "Buy":
        return fp - lp
    return lp - fp


def slippage_vs_signal_pts(fill: dict[str, Any]) -> float | None:
    """Adverse slippage relative to signal price (positive = worse fill)."""
    if "slippage_pts" in fill:
        return float(fill["slippage_pts"])
    fill_price = fill.get("fill_price")
    signal_price = fill.get("signal_price")
    direction = fill.get("direction")
    if fill_price is None or signal_price is None or direction not in ("Buy", "Sell"):
        return None
    fp = float(fill_price)
    sp = float(signal_price)
    if direction == "Buy":
        return fp - sp
    return sp - fp


@dataclass(frozen=True)
class FillComparisonReport:
    backtest_count: int
    reference_count: int
    backtest_median_slip_vs_limit: float | None
    reference_median_slip_vs_limit: float | None
    backtest_median_slip_vs_signal: float | None
    reference_median_slip_vs_signal: float | None
    count_delta: int
    median_slip_vs_limit_delta: float | None
    warnings: tuple[str, ...]


def compare_fill_audits(
    backtest_fills: list[dict[str, Any]],
    reference_fills: list[dict[str, Any]],
) -> FillComparisonReport:
    """Compare aggregate fill statistics between backtest and paper/live logs."""
    bt_limit = [v for f in backtest_fills if (v := slippage_vs_limit_pts(f)) is not None]
    ref_limit = [v for f in reference_fills if (v := slippage_vs_limit_pts(f)) is not None]
    bt_signal = [v for f in backtest_fills if (v := slippage_vs_signal_pts(f)) is not None]
    ref_signal = [v for f in reference_fills if (v := slippage_vs_signal_pts(f)) is not None]

    bt_med_limit = statistics.median(bt_limit) if bt_limit else None
    ref_med_limit = statistics.median(ref_limit) if ref_limit else None
    bt_med_signal = statistics.median(bt_signal) if bt_signal else None
    ref_med_signal = statistics.median(ref_signal) if ref_signal else None

    warnings: list[str] = []
    count_delta = len(backtest_fills) - len(reference_fills)
    if count_delta != 0:
        warnings.append(
            f"fill count mismatch: backtest={len(backtest_fills)} reference={len(reference_fills)}"
        )
    if (
        bt_med_limit is not None
        and ref_med_limit is not None
        and ref_med_limit > bt_med_limit + 0.5
    ):
        warnings.append(
            f"reference median slippage vs limit ({ref_med_limit:.2f}) exceeds backtest "
            f"({bt_med_limit:.2f}) by >0.5 pts — consider raising MockBroker slip params"
        )
    if not reference_fills:
        warnings.append("reference log has zero FILL_AUDIT records")
    if not backtest_fills:
        warnings.append("backtest log has zero FILL_AUDIT records")

    med_delta = None
    if bt_med_limit is not None and ref_med_limit is not None:
        med_delta = ref_med_limit - bt_med_limit

    return FillComparisonReport(
        backtest_count=len(backtest_fills),
        reference_count=len(reference_fills),
        backtest_median_slip_vs_limit=bt_med_limit,
        reference_median_slip_vs_limit=ref_med_limit,
        backtest_median_slip_vs_signal=bt_med_signal,
        reference_median_slip_vs_signal=ref_med_signal,
        count_delta=count_delta,
        median_slip_vs_limit_delta=med_delta,
        warnings=tuple(warnings),
    )


def format_fill_comparison(report: FillComparisonReport) -> str:
    lines = [
        "=== Fill audit comparison (backtest vs reference) ===",
        f"backtest fills:  {report.backtest_count}",
        f"reference fills: {report.reference_count}",
        f"count delta:     {report.count_delta:+d}",
    ]
    if report.backtest_median_slip_vs_limit is not None:
        lines.append(
            f"backtest median slip vs limit:  {report.backtest_median_slip_vs_limit:.2f} pts"
        )
    if report.reference_median_slip_vs_limit is not None:
        lines.append(
            f"reference median slip vs limit: {report.reference_median_slip_vs_limit:.2f} pts"
        )
    if report.median_slip_vs_limit_delta is not None:
        lines.append(
            f"median slip delta (ref - bt):     {report.median_slip_vs_limit_delta:+.2f} pts"
        )
    if report.warnings:
        lines.append("")
        lines.append("warnings:")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)


def hash_audit_records(records: Iterable[tuple[str, str]]) -> str:
    hasher = hashlib.sha256()
    for label, json_part in records:
        hasher.update(normalize_audit_for_hash(label, json_part).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


audit_hash_from_records = hash_audit_records  # back-compat alias


class AuditCaptureHandler(logging.Handler):
    """Capture SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY from trading_engine logger."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        for prefix in AUDIT_PREFIXES:
            if msg.startswith(prefix):
                label = prefix.strip()
                self.records.append((label, msg[len(prefix) :]))
                return


def capture_backtest_audits(
    engine: Any, *, logger_name: str = "trading_engine"
) -> list[tuple[str, str]]:
    """Run BacktestEngine and return captured audit (label, json) pairs."""
    handler = AuditCaptureHandler()
    log = logging.getLogger(logger_name)
    prev_level = log.level
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        engine.run()
    finally:
        log.removeHandler(handler)
        log.setLevel(prev_level)
    return handler.records


__all__ = [
    "AUDIT_PREFIXES",
    "AuditCaptureHandler",
    "FillComparisonReport",
    "audit_hash_from_records",
    "canonical_audit_json",
    "capture_backtest_audits",
    "compare_fill_audits",
    "format_fill_comparison",
    "hash_audit_records",
    "normalize_audit_for_hash",
    "parse_audit_lines",
    "parse_fill_audits",
    "parse_fill_audits_from_file",
    "slippage_vs_limit_pts",
    "slippage_vs_signal_pts",
]
