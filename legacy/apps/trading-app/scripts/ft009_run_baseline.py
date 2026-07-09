"""FT-009: run orb-baseline backtest with opening_range_breakout strategy."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path

from backtest.__main__ import configure_backtest_session_logging, emit_report
from backtest.engine import BacktestEngine
from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.engine_wiring import load_named_strategy
from observability import DailyObservability
from storage.tick_loader import resolve_cli_tick_cache_dates


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _parse_dates(values: list[str]) -> list[datetime.date]:
    return [datetime.date.fromisoformat(d) for d in values]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "orb-baseline"
    parser = argparse.ArgumentParser(description="FT-009 orb-baseline backtest")
    parser.add_argument("--dates", nargs="*", default=None)
    parser.add_argument("--aggregate-0104", action="store_true")
    parser.add_argument("--valid-month", action="store_true")
    parser.add_argument("--holdout-month", action="store_true")
    parser.add_argument(
        "--holdout-v2",
        action="store_true",
        help="2026-05-01..2026-06-30 merged holdout (HOLDOUT_CONTRACT v2)",
    )
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--log-out", type=Path, default=ws / "logs" / "baseline_0104.log")
    parser.add_argument("--report-out", type=Path, default=ws / "reports" / "baseline_0104.json")
    args = parser.parse_args(argv)

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    os.environ["CONFIG_PATH"] = str(args.config.resolve())

    if args.holdout_v2 and args.holdout_month:
        raise SystemExit("use only one of --holdout-month or --holdout-v2")

    holdout_label: str | None = None
        os.environ.setdefault("FT003_HOLDOUT_UNSEAL", "1")
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-05-01",
            to_date="2026-06-30",
        )
        args.log_out = ws / "logs" / "baseline_holdout_v2.log"
        args.report_out = ws / "reports" / "baseline_holdout_v2.json"
        holdout_label = "holdout v2"
    elif args.holdout_month:
        os.environ.setdefault("FT003_HOLDOUT_UNSEAL", "1")
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-05-01",
            to_date="2026-05-31",
        )
        args.log_out = ws / "logs" / "baseline_holdout.log"
        args.report_out = ws / "reports" / "baseline_holdout.json"
        holdout_label = "holdout"
    elif args.aggregate_0104 or (not args.dates and not args.valid_month):
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-01-01",
            to_date="2026-04-30",
        )
        holdout_label = None
    elif args.valid_month:
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-04-01",
            to_date="2026-04-30",
        )
        args.log_out = ws / "logs" / "baseline_valid.log"
        args.report_out = ws / "reports" / "baseline_valid.json"
        holdout_label = None
    else:
        dates = _parse_dates(args.dates)
        holdout_label = None
    if not dates:
        raise SystemExit("no dates to backtest")

    args.log_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    configure_backtest_session_logging(str(args.log_out), truncate=True)

    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    obs = DailyObservability()
    strategy = load_named_strategy("opening_range_breakout", cfg, obs)

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

    if args.report_out.is_file():
        metrics = json.loads(args.report_out.read_text(encoding="utf-8"))
        exp = (metrics.get("performance") or {}).get("expectancy") or {}
        gross = exp.get("expectancy_per_trade_gross")
        net = exp.get("expectancy_per_trade_net")
        trades = exp.get("trade_count")
        qsl = metrics.get("quick_stop_loss_rate_lt_5s")
        if holdout_label is not None:
            _patch_gate_report(
                ws / "gate_report.md", gross, net, trades, qsl, label=holdout_label
            )
        elif args.report_out.name == "baseline_0104.json":
            _patch_gate_report(
                ws / "gate_report.md", gross, net, trades, qsl, label="plugin 01–04"
            )
        print(
            f"FT-009 baseline | trades={trades} gross_exp={gross} net_exp={net} qsl={qsl}",
            flush=True,
        )
    return 0


def _patch_gate_report(
    path: Path,
    gross: float | None,
    net: float | None,
    trades: int | None,
    qsl: float | None,
    *,
    label: str,
) -> None:
    if not path.is_file() or gross is None:
        return
    text = path.read_text(encoding="utf-8")
    net_s = f"{net:.2f}" if net is not None else "—"
    qsl_s = f"{qsl:.1%}" if qsl is not None else "—"
    block = (
        f"\n## Plugin baseline（{label}）\n\n"
        f"| 指標 | 值 |\n|------|-----|\n"
        f"| trades | {trades} |\n"
        f"| gross/趟 | {gross:.2f} |\n"
        f"| net/趟 | {net_s} |\n"
        f"| QSL | {qsl_s} |\n"
    )
    if "## Plugin baseline" not in text:
        text = text.replace("## §Decision", block + "\n## §Decision")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
