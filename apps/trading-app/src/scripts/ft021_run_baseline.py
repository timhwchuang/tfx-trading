"""FT-021: thin wrapper over ``python -m backtest`` for gudt-route-a-baseline."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from backtest.__main__ import main as backtest_main
from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.strategy_bootstrap import load_gudt_probe_rows
from reporting.gudt_wash_probe import load_probe_contexts
from strategy_gudt_route_a import GudtRouteAParams
from strategy_gudt_route_a.stack import summarize_route_a_stack
from strategy_gudt_route_a.stack_params import stack_params_from_gudt


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-route-a-baseline"
    parser = argparse.ArgumentParser(description="FT-021 gudt-route-a baseline backtest")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--log-out", type=Path, default=ws / "logs" / "baseline.log")
    parser.add_argument("--report-out", type=Path, default=ws / "reports" / "baseline.json")
    parser.add_argument("--plans-out", type=Path, default=ws / "reports" / "day_plans.json")
    parser.add_argument("--from-csv", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    os.environ["CONFIG_PATH"] = str(args.config.resolve())
    args.log_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    rows = load_gudt_probe_rows(
        cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        probe_csv_override=args.from_csv,
    )
    day_strs = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(args.code, day_strs, cache_dir=args.cache_dir)
    params = stack_params_from_gudt(GudtRouteAParams.from_runtime_config(cfg))
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)

    bt_argv = [
        "--config",
        str(args.config),
        "--dates-from-cache",
        "--from-date",
        args.from_date,
        "--to-date",
        args.to_date,
        "--code",
        args.code,
        "--cache-dir",
        str(args.cache_dir),
        "--report",
        "--log-file",
        str(args.log_out),
        "--report-json",
        str(args.report_out),
        "--plans-out",
        str(args.plans_out),
    ]
    if args.from_csv is not None:
        bt_argv.extend(["--probe-csv", str(args.from_csv)])

    rc = backtest_main(bt_argv)
    if rc != 0:
        return rc

    cf_net = float(summary["net_total"])
    print(
        f"FT-021 baseline | CF net={cf_net} n={summary['n']} "
        f"extend={summary['extend_days']} flip={summary['flip_days']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
