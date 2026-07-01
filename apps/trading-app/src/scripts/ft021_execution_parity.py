"""FT-021: CF plan vs kernel execution parity (UAT_2m default, extensible slices)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from backtest.__main__ import main as backtest_main
from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from reporting.date_slices import (
    DateRange,
    add_date_slice_arguments,
    artifact_paths,
    backtest_date_cli_args,
    resolve_from_args,
)
from reporting.gudt_execution_compare import (
    append_spot_check_log,
    compare_execution,
    format_net_compare_line,
    write_execution_report_json,
    write_execution_report_md,
)
from reporting.gudt_parity_report import build_research_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _run_baseline(
    *,
    cfg: TradingAppRuntimeConfig,
    date_range: DateRange,
    code: str,
    cache_dir: Path,
    config_path: Path,
    paths: dict[str, Path],
    probe_csv: Path | None,
) -> int:
    os.environ["CONFIG_PATH"] = str(config_path.resolve())
    os.environ.setdefault("FT003_HOLDOUT_UNSEAL", "1")
    paths["baseline_log"].parent.mkdir(parents=True, exist_ok=True)
    bt_argv = [
        "--config",
        str(config_path),
        *backtest_date_cli_args(date_range, code=code, cache_dir=cache_dir),
        "--code",
        code,
        "--cache-dir",
        str(cache_dir),
        "--report",
        "--log-file",
        str(paths["baseline_log"]),
        "--report-json",
        str(paths["baseline_json"]),
        "--plans-out",
        str(paths["day_plans"]),
    ]
    if probe_csv is not None:
        bt_argv.extend(["--probe-csv", str(probe_csv)])
    return int(backtest_main(bt_argv))


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "gudt-route-a-baseline"
    parser = argparse.ArgumentParser(description="FT-021 GUDT execution parity")
    add_date_slice_arguments(parser)
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument(
        "--compare-only",
        action="store_true",
        help="Skip baseline replay; use --log and --plans",
    )
    parser.add_argument("--log", type=Path, default=None, help="baseline log (compare-only)")
    parser.add_argument("--plans", type=Path, default=None, help="day_plans json (compare-only)")
    parser.add_argument(
        "--append-spot-log",
        action="store_true",
        help="Append result row to workspaces/.../reports/SPOT_CHECK_LOG.md",
    )
    args = parser.parse_args(argv)

    if args.cache_dir is None:
        args.cache_dir = root / "tick_cache"

    date_range = resolve_from_args(args, repo_root=root)
    paths = artifact_paths(ws / "reports", ws / "logs", date_range.label)

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))

    if not args.compare_only:
        rc = _run_baseline(
            cfg=cfg,
            date_range=date_range,
            code=args.code,
            cache_dir=args.cache_dir,
            config_path=args.config,
            paths=paths,
            probe_csv=args.from_csv,
        )
        if rc != 0:
            return rc
    else:
        if args.log is not None:
            paths["baseline_log"] = args.log
        if args.plans is not None:
            paths["day_plans"] = args.plans

    if not paths["day_plans"].is_file():
        raise SystemExit(f"day_plans not found: {paths['day_plans']}")
    if not paths["baseline_log"].is_file():
        raise SystemExit(f"baseline log not found: {paths['baseline_log']}")

    day_plans = json.loads(paths["day_plans"].read_text(encoding="utf-8"))
    research = build_research_report(
        cfg,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=date_range.from_date,
        to_date=date_range.to_date,
        day_plans=day_plans,
        probe_csv_override=args.from_csv,
    )
    if date_range.months:
        month_set = set(date_range.months)
        research["picks"] = [
            p for p in research.get("picks", []) if p.get("day", "")[:7] in month_set
        ]

    result = compare_execution(
        day_plans,
        paths["baseline_log"],
        date_range=date_range,
        cf_picks=research.get("picks"),
    )
    write_execution_report_json(paths["execution_parity_json"], result)
    write_execution_report_md(paths["execution_parity_md"], result)

    print(json.dumps(result.to_dict(), indent=2))
    print(format_net_compare_line(result))
    if args.append_spot_log:
        spot_log = ws / "reports" / "SPOT_CHECK_LOG.md"
        cmd_parts = []
        if getattr(args, "spot_check", None):
            cmd_parts.append(f"--spot-check {args.spot_check}")
        elif getattr(args, "months", None):
            cmd_parts.append(f"--months {args.months}")
        elif getattr(args, "from_date", None):
            cmd_parts.append(f"--from {args.from_date} --to {args.to_date}")
        else:
            cmd_parts.append(f"--slice {getattr(args, 'slice_name', 'UAT_2m')}")
        append_spot_check_log(
            spot_log,
            date_label=date_range.label,
            command=" ".join(cmd_parts) or "ft021_execution_parity",
            result=result,
        )
        print(f"SPOT_CHECK_LOG | {spot_log}")
    if result.failures:
        print("EXECUTION_PARITY_FAIL:", "; ".join(result.failures), file=sys.stderr)
        return 1
    print(f"EXECUTION_PARITY_PASS | {paths['execution_parity_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
