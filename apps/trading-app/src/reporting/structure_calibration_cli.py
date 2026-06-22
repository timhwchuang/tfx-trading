"""CLI: P6-SMC-CAL B-class structure filter calibration (log + kbar + tick replay)."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from config import PRODUCT_CODE
from reporting.forward_pnl import ForwardPnlPolicy
from reporting.performance_metrics import FrictionSettings
from reporting.structure_calibration import (
    COUNTERFACTUAL_SCENARIOS,
    TrendHarnessConfig,
    run_b_class_structure_calibration,
    run_structure_sensitivity_sweep,
)
from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR
from storage.tick_loader import DEFAULT_CACHE_DIR
from strategy_vwap_momentum.structure import StructureParams


def _parse_dates(raw: str) -> list[datetime.date]:
    out: list[datetime.date] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.append(datetime.date.fromisoformat(part))
    if not out:
        raise ValueError("at least one --date required")
    return out


def format_structure_calibration_report(result: dict) -> str:
    lines = ["=== P6-SMC-CAL Structure Filter Calibration (B-class) ==="]
    status = result.get("status", "unknown")
    if status in ("no_kbars", "no_armed"):
        lines.append(f"狀態: {status}")
        lines.append(f"code={result.get('code')} dates={result.get('dates')}")
        lines.append(f"notes: {result.get('notes')}")
        return "\n".join(lines)

    lines.append(f"status={status} code={result.get('code')}")
    lines.append(
        f"dates={result.get('dates')} armed={result.get('n_armed')} "
        f"kbars={result.get('kbar_count')} ticks={result.get('tick_count')}"
    )
    lines.append(f"forward_policy={result.get('forward_policy')}")
    lines.append(f"conversion_30s_rate={result.get('conversion_30s_rate')}")
    if result.get("tick_warning"):
        lines.append(f"警告: {result['tick_warning']}")

    cf = result.get("counterfactuals") or {}
    lines.append("")
    lines.append("--- 三組 counterfactual（friction-adjusted net 為主）---")
    for scenario in COUNTERFACTUAL_SCENARIOS:
        m = cf.get(scenario) or {}
        lines.append(
            f"[{scenario}] veto_rate={m.get('veto_rate')} "
            f"(n_veto={m.get('n_veto')} n_allowed={m.get('n_allowed')}) "
            f"delta_net={m.get('delta_expectancy_net')} "
            f"delta_gross={m.get('delta_expectancy')}"
        )

    comp = cf.get("comparison") or {}
    lines.append("")
    lines.append("--- 對照 ---")
    lines.append(
        f"structure_veto_rate={comp.get('structure_veto_rate')} "
        f"trend_veto_rate={comp.get('trend_veto_rate')}"
    )
    lines.append(f"delta_structure_vs_trend={comp.get('delta_structure_vs_trend')}")
    lines.append(f"delta_structure_vs_no_filter={comp.get('delta_structure_vs_no_filter')}")
    lines.append(f"phase3_gate={comp.get('phase3_gate')} ({comp.get('phase3_gate_note')})")

    struct_only = cf.get("structure_only") or {}
    lines.append("")
    lines.append(f"notes: {struct_only.get('notes')}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P6-SMC-CAL B-class: structure vs trend counterfactual harness.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (from apps/trading-app/src):\n"
            "  python -m reporting.structure_calibration_cli logs/uat.log "
            "--dates 2026-06-12\n"
            "  python -m reporting.structure_calibration_cli logs/uat.log "
            "--dates 2026-06-10,2026-06-11,2026-06-12 "
            "--kbar-cache-dir ~/tfx-trading/kbar_cache "
            "--cache-dir ~/tfx-trading/tick_cache "
            "--output-dir reports/smc-cal\n"
            "  python -m reporting.structure_calibration_cli logs/uat.log "
            "--dates 2026-06-12 --friction-enabled --friction-points 2.0\n"
        ),
    )
    parser.add_argument(
        "log_files",
        nargs="+",
        type=Path,
        help="Strategy log(s) with DECISION_AUDIT momentum_armed",
    )
    parser.add_argument(
        "--code",
        default=PRODUCT_CODE,
        help=f"Contract code (default: config product_code={PRODUCT_CODE})",
    )
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated YYYY-MM-DD for kbar_cache + tick_cache",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="tick_cache directory",
    )
    parser.add_argument(
        "--kbar-cache-dir",
        type=Path,
        default=DEFAULT_KBAR_CACHE_DIR,
        help="kbar_cache directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write structure_events.csv + structure_armed_join*.csv here",
    )
    parser.add_argument(
        "--forward-seconds",
        type=int,
        default=1800,
        help="Forward window seconds (default 1800 ≈ 30×1m)",
    )
    parser.add_argument(
        "--forward-mode",
        choices=("fixed_seconds", "fixed_ticks", "session_end"),
        default="fixed_seconds",
    )
    parser.add_argument(
        "--structure-min-strength",
        type=float,
        default=0.0,
        help="structure_min_strength for counterfactual (0.0 = strictest)",
    )
    parser.add_argument(
        "--trend-min-strength",
        type=float,
        default=0.0,
        help="trend_min_strength for trend_only counterfactual",
    )
    parser.add_argument(
        "--friction-enabled",
        action="store_true",
        help="Subtract round-trip friction from forward expectancy",
    )
    parser.add_argument(
        "--friction-points",
        type=float,
        default=2.0,
        help="Round-trip friction points when --friction-enabled",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Run structure_min_strength sensitivity grid on log + kbar + tick replay",
    )
    parser.add_argument(
        "--sweep-output",
        type=Path,
        help="Write sweep_result.jsonl when --sweep",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    for path in args.log_files:
        if not path.is_file():
            print(f"找不到 log 檔: {path}", file=sys.stderr)
            return 1

    dates = _parse_dates(args.dates)
    policy = ForwardPnlPolicy(
        mode=args.forward_mode,
        window_seconds=args.forward_seconds,
    )
    structure_params = StructureParams(structure_min_strength=args.structure_min_strength)
    trend_cfg = TrendHarnessConfig(min_strength=args.trend_min_strength)
    friction = FrictionSettings(
        enabled=args.friction_enabled,
        round_trip_friction_points=args.friction_points,
    )

    result = run_b_class_structure_calibration(
        log_paths=args.log_files,
        code=args.code,
        dates=dates,
        kbar_cache_dir=args.kbar_cache_dir,
        tick_cache_dir=args.cache_dir,
        forward_policy=policy,
        structure_params=structure_params,
        trend_cfg=trend_cfg,
        friction=friction,
        output_dir=args.output_dir,
    )

    if args.sweep:
        sweep_rows = run_structure_sensitivity_sweep(
            log_paths=args.log_files,
            code=args.code,
            dates=dates,
            kbar_cache_dir=args.kbar_cache_dir,
            tick_cache_dir=args.cache_dir,
            forward_policy=policy,
            friction=friction,
            output_path=args.sweep_output,
        )
        result["sensitivity_sweep"] = sweep_rows

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_structure_calibration_report(result))
        if args.sweep and result.get("sensitivity_sweep"):
            print()
            print("=== structure_min_strength sensitivity ===")
            for row in result["sensitivity_sweep"]:
                vm = row.get("veto_metrics") or {}
                print(
                    f"min_strength={row['params'].get('structure_min_strength')} "
                    f"delta_net={vm.get('delta_expectancy_net')} "
                    f"veto_rate={vm.get('veto_rate')} "
                    f"vs_trend={row.get('delta_structure_vs_trend')}"
                )

    status = result.get("status", "")
    if status in ("ok", "ok_no_ticks"):
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())