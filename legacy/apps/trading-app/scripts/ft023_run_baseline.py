"""FT-023: thin wrapper over ``python -m backtest`` for gudt-wash-beta-baseline."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from backtest.__main__ import main as backtest_main
from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.strategy_bootstrap import load_gudt_probe_rows, wash_beta_params_from_config
from reporting.date_slices import add_date_slice_arguments, artifact_paths, backtest_date_cli_args, resolve_from_args
from reporting.gudt_wash_probe import load_probe_contexts
from strategy_gudt_route_a.wash_beta import simulate_wash_beta_day, summarize_wash_beta


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-wash-beta-baseline"
    parser = argparse.ArgumentParser(description="FT-023 gudt-wash-beta baseline backtest")
    add_date_slice_arguments(parser)
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument("--execution-report", action="store_true")
    args = parser.parse_args(argv)

    if args.cache_dir is None:
        args.cache_dir = root / "tick_cache"

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    date_range = resolve_from_args(args, repo_root=root)
    paths = artifact_paths(ws / "reports", ws / "logs", date_range.label)

    os.environ["CONFIG_PATH"] = str(args.config.resolve())
    os.environ.setdefault("FT003_HOLDOUT_UNSEAL", "1")
    paths["baseline_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["baseline_json"].parent.mkdir(parents=True, exist_ok=True)

    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    rows = load_gudt_probe_rows(
        cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=date_range.from_date,
        to_date=date_range.to_date,
        probe_csv_override=args.from_csv,
    )
    if date_range.months:
        month_set = set(date_range.months)
        rows = [r for r in rows if r["day"][:7] in month_set]
    day_strs = sorted({r["day"] for r in rows})
    ctx_by_day = load_probe_contexts(args.code, day_strs, cache_dir=args.cache_dir)
    wb = wash_beta_params_from_config(cfg)
    picks = []
    for day in sorted(ctx_by_day):
        if not (date_range.from_date <= day <= date_range.to_date):
            continue
        sim = simulate_wash_beta_day(ctx_by_day[day], params=wb)
        if sim:
            picks.append({"day": day, "path": "wash_beta", **sim})
    summary = summarize_wash_beta(picks)

    bt_argv = [
        "--config",
        str(args.config),
        *backtest_date_cli_args(date_range, code=args.code, cache_dir=args.cache_dir),
        "--code",
        args.code,
        "--cache-dir",
        str(args.cache_dir),
        "--report",
        "--log-file",
        str(paths["baseline_log"]),
        "--report-json",
        str(paths["baseline_json"]),
        "--plans-out",
        str(paths["day_plans"]),
    ]
    if args.from_csv is not None:
        bt_argv.extend(["--probe-csv", str(args.from_csv)])

    rc = backtest_main(bt_argv)
    if rc != 0:
        return rc

    print(
        f"FT-023 baseline | slice={date_range.label} {date_range.from_date}..{date_range.to_date} "
        f"| CF net={summary['net_total']} n={summary['n']}",
        flush=True,
    )

    if args.execution_report:
        import json as _json

        from reporting.gudt_execution_compare import (
            compare_execution,
            write_execution_report_json,
            write_execution_report_md,
        )
        from reporting.wash_beta_parity_report import build_wash_beta_research_report

        day_plans = _json.loads(paths["day_plans"].read_text(encoding="utf-8"))
        research = build_wash_beta_research_report(
            cfg,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date=date_range.from_date,
            to_date=date_range.to_date,
            day_plans=day_plans,
            probe_csv_override=args.from_csv,
        )
        result = compare_execution(
            day_plans,
            paths["baseline_log"],
            date_range=date_range,
            cf_picks=research.get("picks"),
        )
        write_execution_report_json(paths["execution_parity_json"], result)
        write_execution_report_md(paths["execution_parity_md"], result)
        if result.failures:
            print("EXECUTION_PARITY_FAIL:", "; ".join(result.failures), file=sys.stderr)
            return 1
        print(f"EXECUTION_PARITY_PASS | {paths['execution_parity_json']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
