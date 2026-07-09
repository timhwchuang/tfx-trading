"""FT-021: parity check — counterfactual stack vs unified bootstrap day plans."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings, default_runtime_config
from reporting.date_slices import add_date_slice_arguments, artifact_paths, resolve_from_args
from reporting.gudt_parity_report import build_parity_report, write_json_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-route-a-baseline"
    parser = argparse.ArgumentParser(description="FT-021 parity check (unified bootstrap path)")
    add_date_slice_arguments(parser)
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument(
        "--plans",
        type=Path,
        default=None,
        help="Optional day_plans.json from backtest; default uses bootstrap_gudt_route_a",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.cache_dir is None:
        args.cache_dir = root / "tick_cache"

    date_range = resolve_from_args(args, repo_root=root)
    paths = artifact_paths(ws / "reports", ws / "logs", date_range.label)
    out_path = args.out or (ws / "reports" / f"parity_report_{date_range.label}.json")

    if args.config.is_file():
        os.environ["CONFIG_PATH"] = str(args.config.resolve())
        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config(args.config)))
    else:
        cfg = default_runtime_config()

    day_plans = None
    plans_source = "bootstrap"
    if args.plans is not None and args.plans.is_file():
        day_plans = json.loads(args.plans.read_text(encoding="utf-8"))
        plans_source = "file"
    elif paths["day_plans"].is_file():
        day_plans = json.loads(paths["day_plans"].read_text(encoding="utf-8"))
        plans_source = "file"

    report = build_parity_report(
        cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=date_range.from_date,
        to_date=date_range.to_date,
        day_plans=day_plans,
        probe_csv_override=args.from_csv,
        plans_source=plans_source,
    )
    if date_range.months:
        month_set = set(date_range.months)
        report["picks"] = [p for p in report.get("picks", []) if p.get("day", "")[:7] in month_set]
        report["mismatches"] = [
            m for m in report.get("mismatches", []) if m.get("day", "")[:7] in month_set
        ]
        if "summary" in report and "cf" in report["summary"]:
            picks = report["picks"]
            report["summary"]["cf"]["n"] = len(picks)
            report["summary"]["cf"]["net"] = round(sum(float(p.get("net", 0)) for p in picks), 2)
    write_json_report(out_path, report)

    print(json.dumps(report, indent=2))
    if report["failures"]:
        print("PARITY FAIL:", "; ".join(report["failures"]), file=sys.stderr)
        return 1
    print(f"PARITY PASS | slice={date_range.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
