"""Fill workspaces/<agent>/analysis.md §2/§3 from baseline + sweep artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from reporting.performance_metrics import aggregate_daily_performance, sweep_score_from_kpi
from reporting.performance_metrics import aggregate_daily_performance, sweep_score_from_kpi
from config import SWEEP_DD_PENALTY, SWEEP_SCORE_METRIC, SWEEP_SL_PENALTY


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _aggregate_baseline(report_path: Path) -> dict:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    summaries = data.get("daily_summaries") or []
    total_pnl = sum(float(s.get("pnl", {}).get("daily_pnl_points", 0.0)) for s in summaries)
    total_quick_sl = sum(int(s.get("quick_stop_loss", {}).get("count", 0) or 0) for s in summaries)
    total_exits = sum(int(s.get("fills", {}).get("exit_count", 0) or 0) for s in summaries)
    qsl = total_quick_sl / total_exits if total_exits else None
    perf = aggregate_daily_performance(summaries)
    kpi = {
        "daily_pnl_points": round(total_pnl, 2),
        "quick_stop_loss_rate": qsl,
        "trade_count": total_exits,
        "day_count": len(summaries),
        "performance_aggregate": perf,
    }
    kpi["valid_score"] = sweep_score_from_kpi(
        kpi,
        metric=SWEEP_SCORE_METRIC,
        dd_penalty=SWEEP_DD_PENALTY,
        sl_penalty=SWEEP_SL_PENALTY,
    )
    return kpi


def _pct(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _replace_section(text: str, header: str, next_header: str, body: str) -> str:
    pattern = rf"## {re.escape(header)}.*?(?=^## {re.escape(next_header)})"
    replacement = f"## {header}\n\n{body.strip()}\n\n"
    out, n = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL | re.MULTILINE)
    if n != 1:
        raise ValueError(f"could not patch section {header!r}")
    return out


def _fill_baseline(agent: str, root: Path, text: str) -> str:
    report = root / "workspaces" / agent / "reports" / "baseline_valid.json"
    if not report.is_file():
        raise FileNotFoundError(report)
    kpi = _aggregate_baseline(report)
    perf = kpi["performance_aggregate"]
    qsl = kpi.get("quick_stop_loss_rate")
    score = float(kpi["valid_score"])
    body = f"""| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | {score:.2f} | expectancy_net − sl_penalty×QSL |
| daily_pnl_points | {kpi['daily_pnl_points']:.1f} | valid 區間毛點數合計（{kpi['day_count']} 日） |
| expectancy_net | {perf.get('expectancy_per_trade_net', 0):.2f} | 摩擦 5 點/趟後 |
| sharpe_net | {perf.get('sharpe_net', '—')} | per_trade |
| max_drawdown_points | {perf.get('max_drawdown_points', '—')} | 累積淨 MDD |
| quick_stop_loss_rate | {_pct(qsl)} | |
| trade_count | {kpi['trade_count']} | exit 數 |
| day_count | {kpi['day_count']} | 2026-04 全月 |

**交易員一句話評論**：預設 config 基線已建立；valid_score {score:.2f}，QSL {_pct(qsl)}，樣本 {kpi['trade_count']} 筆。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否"""
    if agent == "agent-regime":
        body = body.replace(
            "| valid_score |",
            "| valid_score |",
        ).replace(
            "| 指標 | Baseline 值 | 備註 |",
            "| 指標 | Baseline 值 | 備註 |\n|------|-------------|------|\n| valid_score | "
            f"{score:.2f} | filter **關**（UAT 預設） |\n| daily_pnl_points | {kpi['daily_pnl_points']:.1f} | |\n"
            f"| trade_count | {kpi['trade_count']} | |\n| day_count | {kpi['day_count']} | |\n\n"
            "**交易員一句話評論**：filter 關基線；作為 regime overlay 研究對照。\n\n"
            "**是否值得進入 Sweep**：  \n- [x] 是  \n- [ ] 否\n\n<!-- patched -->",
        )
        # regime uses shorter table - rebuild cleanly
        body = f"""| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | {score:.2f} | filter **關**（UAT 預設） |
| daily_pnl_points | {kpi['daily_pnl_points']:.1f} | |
| trade_count | {kpi['trade_count']} | |
| day_count | {kpi['day_count']} | |

**交易員一句話評論**：filter 關基線；作為 trend overlay 研究對照。

**是否值得進入 Sweep**：  
- [x] 是  
- [ ] 否"""
    return _replace_section(text, "2. Baseline 表現（Baseline Performance）", "3. Sweep 結果與關鍵發現", body)


def _sweep_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("valid_score", float("-inf")), reverse=True)
    return rows


def _baseline_score(root: Path, agent: str) -> float:
    report = root / "workspaces" / agent / "reports" / "baseline_valid.json"
    return float(_aggregate_baseline(report)["valid_score"])


def _execution_sensitivity_notes(rows: list[dict]) -> str:
    from collections import defaultdict

    by_trail: dict[int, list[float]] = defaultdict(list)
    by_ioc: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        p = row["params"]
        by_trail[int(p["trail_points"])].append(float(row["valid_score"]))
        by_ioc[int(p["ioc_slippage_points"])].append(float(row["valid_score"]))

    best_trail = max(by_trail, key=lambda t: max(by_trail[t]))
    worst_trail = min(by_trail, key=lambda t: max(by_trail[t]))
    best_ioc = max(by_ioc, key=lambda i: max(by_ioc[i]))
    top = rows[0]
    vk = top["valid_kpi"]
    perf = vk.get("performance_aggregate") or {}
    gross = perf.get("total_pnl_gross")
    net = perf.get("total_pnl_net")
    return (
        f"- **trail_points**：{best_trail} 組 valid_score 最佳（{worst_trail} 最差）。\n"
        f"- **ioc_slippage_points**：{best_ioc} 組平均 valid_score 最高。\n"
        f"- **冠軍毛/淨**：gross PnL {gross} / net {net}（valid）。\n"
        f"- **交易員覆核**：（請補 skew / 是否值得與出場軸協同。）"
    )


def _fill_sweep_execution(rows: list[dict], baseline_score: float) -> str:
    lines = [
        "| Rank | valid_score | params | quick_stop_loss_rate | vs Baseline |",
        "|------|-------------|--------|----------------------|-------------|",
    ]
    for i, row in enumerate(rows[:3], start=1):
        vk = row["valid_kpi"]
        qsl = vk.get("quick_stop_loss_rate")
        delta = float(row["valid_score"]) - baseline_score
        lines.append(
            f"| {i} | {row['valid_score']:.2f} | `{row['params']}` | {_pct(qsl)} | "
            f"valid_score **{delta:+.2f}** |"
        )
    worst = min(rows, key=lambda r: r["valid_score"])
    wq = worst["valid_kpi"].get("quick_stop_loss_rate")
    top_delta = float(rows[0]["valid_score"]) - baseline_score
    body = "\n".join(lines) + f"""

**最差 1 組**：`{worst['params']}` — valid_score **{worst['valid_score']:.2f}**；QSL {_pct(wq)}。

**參數敏感度**（由 sweep_result.jsonl 自動彙總）：
{_execution_sensitivity_notes(rows)}

**最有價值的一個發現**：冠軍 `{rows[0]['params']}`，valid_score **{rows[0]['valid_score']:.2f}**（vs baseline **{top_delta:+.2f}**）。請交易員覆核 gross/net 與出場軸協同。"""
    return body


def _fill_sweep_risk_exit(rows: list[dict], baseline_score: float) -> str:
    lines = [
        "| Rank | valid_score | params | max_drawdown_points | quick_stop_loss_rate | vs Baseline |",
        "|------|-------------|--------|---------------------|----------------------|-------------|",
    ]
    for i, row in enumerate(rows[:3], start=1):
        vk = row["valid_kpi"]
        perf = vk.get("performance_aggregate") or {}
        mdd = perf.get("max_drawdown_points", "—")
        qsl = vk.get("quick_stop_loss_rate")
        delta = float(row["valid_score"]) - baseline_score
        lines.append(
            f"| {i} | {row['valid_score']:.2f} | `{row['params']}` | {mdd} | {_pct(qsl)} | "
            f"**{delta:+.2f}** |"
        )
    worst = min(rows, key=lambda r: r["valid_score"])
    wperf = worst["valid_kpi"].get("performance_aggregate") or {}
    body = "\n".join(lines) + f"""

**最差 1 組**：`{worst['params']}` — valid_score **{worst['valid_score']:.2f}**；MDD {wperf.get('max_drawdown_points', '—')}。

**參數敏感度**：（由 sweep 排名自動填入；請回來後用交易員視角覆核 skew / 連虧結構。）

**最有價值的一個發現**（出場結構 / skew 語言）：top 組合見上表；重點比較 `fixed_tp_points` × `trail_points` × `max_consecutive_loss` 對 MDD 與 QSL 的三角權衡。"""
    return body


def _fill_sweep_regime(rows: list[dict], baseline_score: float) -> str:
    lines = [
        "| Rank | valid_score | params | veto 相關 | vs Baseline |",
        "|------|-------------|--------|-----------|-------------|",
    ]
    for i, row in enumerate(rows[:3], start=1):
        veto = row.get("veto_metrics") or {}
        vr = veto.get("veto_rate")
        veto_note = f"veto_rate={vr:.2%}" if isinstance(vr, (int, float)) else str(veto.get("note", "—"))
        delta = float(row["valid_score"]) - baseline_score
        lines.append(
            f"| {i} | {row['valid_score']:.2f} | `{row['params']}` | {veto_note} | **{delta:+.2f}** |"
        )
    worst = min(rows, key=lambda r: r["valid_score"])
    body = "\n".join(lines) + f"""

**最差 1 組**：`{worst['params']}` — valid_score **{worst['valid_score']:.2f}**。

**參數敏感度**：（trend_min_strength / trend_slope_min 對 veto 率與進場數；**研究 overlay，非 Pilot 開 filter 建議**。）

**最有價值的一個發現**：見 `veto_metrics`；**不得**宣稱 valid 贏了即可上線開 filter（CAL-8）。"""
    return body


def _fill_sweep(agent: str, root: Path, text: str) -> str:
    result = root / "workspaces" / agent / "sweep_result.jsonl"
    rows = _sweep_rows(result)
    baseline_score = _baseline_score(root, agent)
    if agent == "agent-execution":
        body = _fill_sweep_execution(rows, baseline_score)
    elif agent == "agent-risk-exit":
        body = _fill_sweep_risk_exit(rows, baseline_score)
    elif agent == "agent-regime":
        body = _fill_sweep_regime(rows, baseline_score)
    else:
        raise ValueError(f"unsupported agent {agent}")
    return _replace_section(text, "3. Sweep 結果與關鍵發現", "4. Overfitting 與穩健性評估", body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent")
    parser.add_argument("--sections", default="baseline,sweep", help="baseline,sweep")
    args = parser.parse_args(argv)

    root = _repo_root()
    analysis = root / "workspaces" / args.agent / "analysis.md"
    text = analysis.read_text(encoding="utf-8")
    if not re.search(r"\*\*分析日期\*\*：\s*\S", text):
        text = re.sub(
            r"\*\*分析日期\*\*：.*",
            f"**分析日期**：{date.today().isoformat()}",
            text,
            count=1,
        )

    sections = {s.strip() for s in args.sections.split(",") if s.strip()}
    if "baseline" in sections:
        text = _fill_baseline(args.agent, root, text)
    if "sweep" in sections:
        text = _fill_sweep(args.agent, root, text)

    analysis.write_text(text, encoding="utf-8")
    print(f"updated {analysis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
