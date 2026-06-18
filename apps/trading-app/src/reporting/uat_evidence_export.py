"""Export APP.md Phase 3/4 evidence CSVs from saved UAT JSON reports."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from reporting.evidence_csv import (
    BROKER_COLUMNS,
    BROKER_DIFF_REVIEW_THRESHOLD,
    TICK_COLUMNS,
    read_evidence_csv,
)
from reporting.metrics_extract import log_daily_pnl, parse_optional_float, type0_pct
from reporting.uat_report import load_metrics_from_json_paths
from storage.cache_paths import DEFAULT_UAT_EVIDENCE_DIR


def classify_tick_tier(type0_pct_value: float | None) -> str:
    if type0_pct_value is None:
        return ""
    if type0_pct_value < 30:
        return "low_lt30"
    if type0_pct_value <= 40:
        return "mid_30_40"
    return "high_gt40"


def _format_optional_number(value: float | None, *, places: int = 2) -> str:
    if value is None:
        return ""
    return f"{round(value, places):.{places}f}"


def _format_conversion_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{round(value * 100.0, 2):.2f}"


def load_broker_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    return read_evidence_csv(
        path,
        [
            "date",
            "broker_daily_pnl_pts",
            "broker_source_note",
            "explained_y_or_n",
            "explanation",
        ],
    )


def _resolve_broker_override(
    existing: dict[str, str] | None,
    incoming: dict[str, str] | None,
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in (existing, incoming):
        if not source:
            continue
        for key in (
            "broker_daily_pnl_pts",
            "broker_source_note",
            "explained_y_or_n",
            "explanation",
        ):
            if source.get(key):
                merged[key] = source[key]
    return merged


def build_broker_row(
    date: str,
    data: dict,
    *,
    broker_override: dict[str, str] | None = None,
) -> dict[str, str]:
    override = broker_override or {}
    log_pnl = log_daily_pnl(data)
    broker_pnl_raw = override.get("broker_daily_pnl_pts", "")
    broker_pnl, parse_err = parse_optional_float(broker_pnl_raw)

    diff_pts: float | None = None
    if broker_pnl is not None and log_pnl is not None:
        diff_pts = round(broker_pnl - log_pnl, 2)

    explained = override.get("explained_y_or_n", "")
    explanation = override.get("explanation", "")
    if parse_err:
        explanation = explanation or parse_err
    elif not explained and diff_pts is not None:
        if abs(diff_pts) <= BROKER_DIFF_REVIEW_THRESHOLD:
            explained = "Y"
            explanation = explanation or "within 0.5pt threshold"
        else:
            explained = "N"
            explanation = (
                explanation or f"diff {diff_pts:+.2f}pt exceeds 0.5pt — review required"
            )

    return {
        "date": date,
        "broker_daily_pnl_pts": broker_pnl_raw,
        "log_daily_pnl_points": _format_optional_number(log_pnl),
        "diff_pts": _format_optional_number(diff_pts),
        "round_trips": str(int(data.get("completed_rounds") or 0)),
        "broker_source_note": override.get("broker_source_note", ""),
        "explained_y_or_n": explained,
        "explanation": explanation,
    }


def build_tick_row(date: str, data: dict) -> dict[str, str]:
    type0 = type0_pct(data)
    exp = (data.get("performance") or {}).get("expectancy") or {}
    conversion = data.get("momentum_to_entry_conversion")
    rounds = int(data.get("completed_rounds") or 0)
    entry_signals = int(data.get("entry_signals") or 0)

    notes: list[str] = []
    if type0 is None:
        notes.append("missing tick_type in report JSON")
    if rounds == 0:
        notes.append("0 completed round-trips")

    return {
        "date": date,
        "type0_pct": _format_optional_number(type0),
        "tier": classify_tick_tier(type0),
        "signal_intents": str(entry_signals),
        "fills": str(rounds),
        "conversion_pct": _format_conversion_pct(conversion if conversion is not None else None),
        "expectancy_gross_pts": _format_optional_number(
            float(exp["expectancy_per_trade_gross"])
            if exp.get("expectancy_per_trade_gross") is not None
            else None
        ),
        "expectancy_net_pts": _format_optional_number(
            float(exp["expectancy_per_trade_net"])
            if exp.get("expectancy_per_trade_net") is not None
            else None
        ),
        "notes": "; ".join(notes),
    }


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_broker_reconciliation_csv(
    reports: list[tuple[str, dict]],
    output_path: Path,
    *,
    broker_overrides: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    overrides = broker_overrides or {}
    existing = read_evidence_csv(output_path, BROKER_COLUMNS)
    merged_rows: dict[str, dict[str, str]] = dict(existing)

    for date, data in reports:
        override = _resolve_broker_override(existing.get(date), overrides.get(date))
        merged_rows[date] = build_broker_row(date, data, broker_override=override)

    ordered = [merged_rows[date] for date in sorted(merged_rows)]
    _write_csv(output_path, BROKER_COLUMNS, ordered)
    return ordered


def write_tick_stratification_csv(
    reports: list[tuple[str, dict]],
    output_path: Path,
) -> list[dict[str, str]]:
    existing = read_evidence_csv(output_path, TICK_COLUMNS)
    merged_rows: dict[str, dict[str, str]] = dict(existing)

    for date, data in reports:
        generated = build_tick_row(date, data)
        if date in existing and existing[date].get("notes"):
            generated["notes"] = existing[date]["notes"]
        merged_rows[date] = generated

    ordered = [merged_rows[date] for date in sorted(merged_rows)]
    _write_csv(output_path, TICK_COLUMNS, ordered)
    return ordered


def export_evidence(
    report_paths: list[Path],
    *,
    mode: str,
    broker_output: Path,
    tick_output: Path,
    broker_data: Path | None = None,
) -> dict[str, Any]:
    reports = load_metrics_from_json_paths(report_paths)
    broker_overrides = load_broker_overrides(broker_data)
    result: dict[str, Any] = {"mode": mode, "report_count": len(reports)}

    if mode in ("broker", "both"):
        rows = write_broker_reconciliation_csv(
            reports,
            broker_output,
            broker_overrides=broker_overrides,
        )
        result["broker"] = {"path": str(broker_output), "rows": len(rows)}
    if mode in ("tick", "both"):
        rows = write_tick_stratification_csv(reports, tick_output)
        result["tick"] = {"path": str(tick_output), "rows": len(rows)}
    return result


def main(argv: list[str] | None = None) -> int:
    default_broker = DEFAULT_UAT_EVIDENCE_DIR / "phase3_weekly" / "broker_reconciliation.csv"
    default_tick = DEFAULT_UAT_EVIDENCE_DIR / "phase4_stress" / "tick_quality_stratification.csv"

    parser = argparse.ArgumentParser(
        description="Export broker reconciliation and tick stratification CSVs from UAT JSON reports."
    )
    parser.add_argument(
        "mode",
        choices=["broker", "tick", "both"],
        help="Which evidence CSV to export",
    )
    parser.add_argument(
        "report_files",
        nargs="+",
        type=Path,
        help="reports/day*.json from `python -m reporting <log> --json`",
    )
    parser.add_argument(
        "--broker-output",
        type=Path,
        default=default_broker,
        help=f"Broker reconciliation CSV path (default: {default_broker})",
    )
    parser.add_argument(
        "--tick-output",
        type=Path,
        default=default_tick,
        help=f"Tick stratification CSV path (default: {default_tick})",
    )
    parser.add_argument(
        "--broker-data",
        type=Path,
        default=None,
        help="Optional CSV with date,broker_daily_pnl_pts,broker_source_note,...",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print export summary as JSON",
    )
    args = parser.parse_args(argv)

    for path in args.report_files:
        if not path.is_file():
            print(f"找不到檔案: {path}", file=sys.stderr)
            return 1

    summary = export_evidence(
        args.report_files,
        mode=args.mode,
        broker_output=args.broker_output,
        tick_output=args.tick_output,
        broker_data=args.broker_data,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if "broker" in summary:
            print(
                f"Broker reconciliation: {summary['broker']['rows']} rows → {summary['broker']['path']}"
            )
        if "tick" in summary:
            print(
                f"Tick stratification: {summary['tick']['rows']} rows → {summary['tick']['path']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())