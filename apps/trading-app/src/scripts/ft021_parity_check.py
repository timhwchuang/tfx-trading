"""FT-021: parity check — counterfactual stack vs unified bootstrap day plans."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings, default_runtime_config
from reporting.gudt_parity_report import build_parity_report, write_json_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-route-a-baseline"
    parser = argparse.ArgumentParser(description="FT-021 parity check (unified bootstrap path)")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument(
        "--plans",
        type=Path,
        default=None,
        help="Optional day_plans.json from backtest; default uses bootstrap_gudt_route_a",
    )
    parser.add_argument("--out", type=Path, default=ws / "reports" / "parity_report.json")
    args = parser.parse_args(argv)

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

    report = build_parity_report(
        cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        day_plans=day_plans,
        probe_csv_override=args.from_csv,
        plans_source=plans_source,
    )
    write_json_report(args.out, report)

    print(json.dumps(report, indent=2))
    if report["failures"]:
        print("PARITY FAIL:", "; ".join(report["failures"]), file=sys.stderr)
        return 1
    print("PARITY PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
