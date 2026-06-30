"""FT-021: run gudt-route-a-baseline backtest with replay plans from CF stack."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from backtest.__main__ import configure_backtest_session_logging, emit_report
from backtest.engine import BacktestEngine
from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.engine_wiring import load_named_strategy
from integrations.gudt_replay_planner import build_replay_plans_for_range
from observability import DailyObservability
from strategy_gudt_route_a import GudtRouteAParams
from strategy_gudt_route_a.stack import summarize_route_a_stack
from strategy_gudt_route_a.stack_params import stack_params_from_gudt
from reporting.gudt_wash_probe import WashProbeTuning, load_probe_contexts, read_probe_csv, run_probe_range
from storage.tick_loader import resolve_cli_tick_cache_dates


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _parse_dates(values: list[str]) -> list[datetime.date]:
    return [datetime.date.fromisoformat(d) for d in values]


def _load_probe_rows(
    *,
    root: Path,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    from_csv: Path | None,
) -> list[dict]:
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    csv_path = from_csv or reports / "gudt_wash_probe_merged_202505_202606.csv"
    if csv_path.is_file():
        rows = read_probe_csv(csv_path)
        return [r for r in rows if from_date <= r["day"] <= to_date]
    pad_from = (datetime.date.fromisoformat(from_date) - datetime.timedelta(days=45)).isoformat()
    rows = run_probe_range(
        code=code,
        from_date=pad_from,
        to_date=to_date,
        cache_dir=cache_dir,
        tuning=WashProbeTuning(),
    )
    return [r for r in rows if from_date <= r["day"] <= to_date]


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

    dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    if not dates:
        raise SystemExit("no dates to backtest")

    os.environ["CONFIG_PATH"] = str(args.config.resolve())
    args.log_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    rows = _load_probe_rows(
        root=root,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        from_csv=args.from_csv,
    )
    day_strs = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(args.code, day_strs, cache_dir=args.cache_dir)
    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    obs = DailyObservability()
    gudt_params = GudtRouteAParams.from_runtime_config(cfg)
    params = stack_params_from_gudt(gudt_params)
    summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)
    day_plans = build_replay_plans_for_range(rows, ctx_by_day, params=params)

    plans_payload = {
        day: {
            "path": p.path,
            "skipped": p.skipped,
            "events": [
                {"ts": e.ts, "action": e.action, "price": e.price, "leg": e.leg, "reason": e.reason}
                for e in p.events
            ],
            "meta": p.meta,
        }
        for day, p in day_plans.items()
    }
    args.plans_out.write_text(json.dumps(plans_payload, indent=2), encoding="utf-8")

    configure_backtest_session_logging(str(args.log_out), truncate=True)
    strategy = load_named_strategy("gudt_route_a", cfg, obs, day_plans=day_plans)

    engine = BacktestEngine(
        args.code,
        dates,
        cache_dir=args.cache_dir,
        strategy=strategy,
        runtime_config=cfg,
        obs=obs,
    )
    engine.run()
    emit_report(args.log_out, print_report=True, json_path=args.report_out)

    cf_net = float(summary["net_total"])
    print(
        f"FT-021 baseline | CF net={cf_net} n={summary['n']} "
        f"extend={summary['extend_days']} flip={summary['flip_days']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
