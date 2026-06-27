"""FT-004: run mc-baseline backtest with momentum_continuation strategy."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

from backtest.__main__ import (
    configure_backtest_session_logging,
    emit_report,
    report_json_path_for_log,
)
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
    ws = root / "workspaces" / "mc-baseline"
    parser = argparse.ArgumentParser(description="FT-004 mc-baseline backtest")
    parser.add_argument(
        "--dates",
        nargs="*",
        default=None,
        help="Trade dates YYYY-MM-DD; omit with --valid-month for full April 2026 valid",
    )
    parser.add_argument(
        "--valid-month",
        action="store_true",
        help="Use all tick_cache dates in 2026-04 (valid)",
    )
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument(
        "--config",
        type=Path,
        default=ws / "config" / "config.yaml",
    )
    parser.add_argument(
        "--log-out",
        type=Path,
        default=ws / "logs" / "baseline_valid.log",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=ws / "reports" / "baseline_valid.json",
    )
    args = parser.parse_args(argv)

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    os.environ["CONFIG_PATH"] = str(args.config.resolve())

    if args.valid_month or not args.dates:
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-04-01",
            to_date="2026-04-30",
        )
    else:
        dates = _parse_dates(args.dates)
    if not dates:
        raise SystemExit("no dates to backtest")

    args.log_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)

    configure_backtest_session_logging(str(args.log_out), truncate=True)

    app_settings = load_config(args.config)
    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    obs = DailyObservability()
    strategy = load_named_strategy("momentum_continuation", cfg, obs)

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
        _write_gate_report(ws / "gate_report.md", gross, net, trades, qsl)
        print(
            f"FT-004 baseline | trades={trades} gross_exp={gross} net_exp={net} qsl={qsl}",
            flush=True,
        )
    return 0


def _write_gate_report(
    path: Path,
    gross: float | None,
    net: float | None,
    trades: int | None,
    qsl: float | None,
) -> None:
    def _pass_g1(v: float | None) -> str:
        return "☑" if v is not None and v > 5 else "☐"

    def _pass(v: float | None, ok) -> str:
        return "☑" if v is not None and ok(v) else "☐"

    text = path.read_text(encoding="utf-8")
    if gross is not None:
        text = re.sub(
            r"\| gross expectancy/趟 \| [^|]+ \| [☐☑] \|",
            f"| gross expectancy/趟 | {gross:.2f} | {_pass_g1(gross)} |",
            text,
            count=1,
        )
    if net is not None:
        text = re.sub(
            r"\| net expectancy/趟 \| [^|]+ \| [☐☑] \|",
            f"| net expectancy/趟 | {net:.2f} | {_pass(net, lambda x: x > 0)} |",
            text,
            count=1,
        )
    if trades is not None:
        text = re.sub(
            r"\| trade_count（valid 月） \| [^|]+ \|",
            f"| trade_count（valid 月） | {trades} |",
            text,
            count=1,
        )
        text = re.sub(
            r"\| trade_count \| [^|]+ \| [☐☑] \|",
            f"| trade_count | {trades} | {_pass(trades, lambda x: x < 100)} |",
            text,
            count=1,
        )
    if qsl is not None:
        text = re.sub(
            r"\| quick_stop_loss_rate \| [^|]+ \| [☐☑] \|",
            f"| quick_stop_loss_rate | {qsl:.1%} | {_pass(qsl, lambda x: x < 0.25)} |",
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
