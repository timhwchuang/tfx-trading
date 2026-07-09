"""FT-006: run vsf-baseline backtest with vwap_stretch_fade strategy."""

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
    ws = root / "workspaces" / "vsf-baseline"
    parser = argparse.ArgumentParser(description="FT-006 vsf-baseline backtest")
    parser.add_argument("--dates", nargs="*", default=None)
    parser.add_argument("--valid-month", action="store_true")
    parser.add_argument("--holdout-month", action="store_true")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--config", type=Path, default=ws / "config" / "config.yaml")
    parser.add_argument("--log-out", type=Path, default=ws / "logs" / "baseline_valid.log")
    parser.add_argument("--report-out", type=Path, default=ws / "reports" / "baseline_valid.json")
    args = parser.parse_args(argv)

    if not args.config.is_file():
        raise SystemExit(f"config not found: {args.config}")

    os.environ["CONFIG_PATH"] = str(args.config.resolve())

    if args.holdout_month:
        os.environ.setdefault("FT003_HOLDOUT_UNSEAL", "1")
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=args.code,
            cache_dir=args.cache_dir,
            from_date="2026-05-01",
            to_date="2026-05-31",
        )
        if args.log_out == ws / "logs" / "baseline_valid.log":
            args.log_out = ws / "logs" / "baseline_holdout.log"
        if args.report_out == ws / "reports" / "baseline_valid.json":
            args.report_out = ws / "reports" / "baseline_holdout.json"
    elif args.valid_month or not args.dates:
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
    strategy = load_named_strategy("vwap_stretch_fade", cfg, obs)

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
        if args.holdout_month:
            _write_holdout_gate_report(ws / "gate_report.md", gross, net, trades, qsl)
        else:
            _write_gate_report(ws / "gate_report.md", gross, net, trades, qsl)
        label = "holdout" if args.holdout_month else "baseline"
        print(
            f"FT-006 {label} | trades={trades} gross_exp={gross} net_exp={net} qsl={qsl}",
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

    if not path.is_file():
        return
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


def _write_holdout_gate_report(
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

    g1 = _pass_g1(gross)
    g2 = _pass(net, lambda x: x > 0)
    g3 = _pass(float(trades) if trades is not None else None, lambda x: x < 100)
    g4 = _pass(qsl, lambda x: x < 0.25)
    all_pass = all(c == "☑" for c in (g1, g2, g3, g4))
    verdict = "**通過**" if all_pass else "**未過**（overfit suspect 或 edge 消失）"

    gross_s = f"{gross:.2f}" if gross is not None else "TBD"
    net_s = f"{net:.2f}" if net is not None else "TBD"
    trades_s = str(trades) if trades is not None else "TBD"
    qsl_s = f"{qsl:.1%}" if qsl is not None else "TBD"

    section = f"""## Holdout 2026-05（封印解封 · plugin baseline）

| 指標 | 門檻 | 值 | Pass |
|------|------|-----|------|
| gross expectancy/趟 | > 5 | **{gross_s}** | {g1} |
| net expectancy/趟 | > 0 | **{net_s}** | {g2} |
| trade_count | < 100/月 | **{trades_s}** | {g3} |
| quick_stop_loss_rate | < 25% | **{qsl_s}** | {g4} |

**Holdout**：{verdict} · 產物：[`reports/baseline_holdout.json`](reports/baseline_holdout.json)

---

"""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## Holdout 2026-05"
    if marker in text:
        text = re.sub(
            r"## Holdout 2026-05[\s\S]*?(?=\n## |\n---\n\n## §Decision|\Z)",
            section.rstrip() + "\n\n",
            text,
            count=1,
        )
    else:
        text = text.replace("\n---\n\n## §Decision", f"\n---\n\n{section}## §Decision")
    if gross is not None and net is not None and trades is not None:
        text = re.sub(
            r"\| Plugin baseline \| 82 趟；gross \*\*\+5\.43\*\*/趟、net \*\*\+0\.43\*\*/趟；QSL \*\*6\.1%\*\* \|",
            f"| Plugin baseline | valid 82 趟 gross **+5.43**；holdout {trades} 趟 gross **{gross:+.2f}**、net **{net:+.2f}** |",
            text,
            count=1,
        )
        if all_pass:
            text = re.sub(
                r"\| 決策 \| \*\*Go — Pilot-prep\*\*[^|]*\|",
                "| 決策 | **Go — Pilot-prep**（valid + holdout G1–G4 全過；UAT 切換待人類簽核） |",
                text,
                count=1,
            )
        else:
            text = re.sub(
                r"\| 決策 \| \*\*Go — Pilot-prep\*\*[^|]*\|",
                "| 決策 | **Holdout 未過** — 維持 Pilot-prep 凍結；勿 sweep on valid、勿切 UAT |",
                text,
                count=1,
            )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
