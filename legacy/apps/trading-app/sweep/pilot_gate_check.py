"""APP.md Phase 5 Pilot Readiness Gate — automated checklist from saved UAT reports."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reporting.evidence_csv import (
    evaluate_broker_reconciliation_csv,
    evaluate_tick_stratification_csv,
)
from reporting.metrics_extract import daily_pnl_series, per_trade_return_series
from reporting.performance_metrics import compute_cumulative_risk_progression, compute_sharpe_sortino
from reporting.uat_report import load_metrics_from_json_paths
from storage.cache_paths import DEFAULT_UAT_EVIDENCE_DIR

# Thresholds from docs/uat/APP.md Phase 5 (SSOT).
MIN_TRADING_DAYS = 20
MIN_ROUND_TRIPS_TOTAL = 80
MIN_ROUND_TRIPS_RECENT_10 = 35
MIN_EXPECTANCY_NET_RECENT = 0.35
MIN_EXPECTANCY_NET_HEALTH = 0.30
MIN_SHARPE = 0.60
MAX_MDD_BUDGET_PCT = 70.0
DENSITY_WINDOW_DAYS = 5
DENSITY_MIN_ROUND_TRIPS = 8
BIG_LOSS_DAILY_PNL_POINTS = -20.0
CONSECUTIVE_BIG_LOSS_DAYS = 3

CRITICAL_ALERT_RE = re.compile(r"ALERT \[CRITICAL\]")
LOG_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DAILY_SUMMARY_DATE_RE = re.compile(r'DAILY_SUMMARY .*"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"')


@dataclass
class GateCheck:
    id: str
    label: str
    passed: bool
    detail: str
    manual: bool = False


@dataclass
class PilotGateResult:
    passed: bool
    checks: list[GateCheck] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "checks": [
                {
                    "id": c.id,
                    "label": c.label,
                    "passed": c.passed,
                    "detail": c.detail,
                    "manual": c.manual,
                }
                for c in self.checks
            ],
        }


def _weighted_expectancy(
    reports: list[tuple[str, dict]],
    *,
    field_name: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for _date, data in reports:
        rounds = int(data.get("completed_rounds") or 0)
        exp = (data.get("performance") or {}).get("expectancy") or {}
        value = exp.get(field_name)
        if rounds > 0 and value is not None:
            numerator += float(value) * rounds
            denominator += rounds
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _has_consecutive_big_losses(
    daily_pnls: list[tuple[str, float]],
    *,
    threshold: float,
    streak: int,
) -> tuple[bool, str]:
    run = 0
    worst_streak_dates: list[str] = []
    current_dates: list[str] = []
    for date, pnl in daily_pnls:
        if pnl <= threshold:
            run += 1
            current_dates.append(date)
            if run >= streak:
                worst_streak_dates = list(current_dates[-streak:])
        else:
            run = 0
            current_dates = []
    if worst_streak_dates:
        return True, f"連續 {streak} 日 ≤ {threshold} 點：{', '.join(worst_streak_dates)}"
    return False, f"無連續 {streak} 日 ≤ {threshold} 點"


def _count_critical_alerts(
    log_path: Path | None,
    *,
    recent_dates: set[str],
) -> tuple[int | None, str]:
    if log_path is None:
        return None, "未提供 --log-file（需人工確認過去 10 交易日零 Critical）"
    if not log_path.is_file():
        return None, f"找不到 log：{log_path}"

    current_date: str | None = None
    recent_critical = 0
    total_critical = 0

    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        summary_match = DAILY_SUMMARY_DATE_RE.search(line)
        if summary_match:
            current_date = summary_match.group(1)
        else:
            date_match = LOG_DATE_RE.search(line)
            if date_match:
                current_date = date_match.group(1)

        if CRITICAL_ALERT_RE.search(line):
            total_critical += 1
            if current_date is None or current_date in recent_dates:
                recent_critical += 1

    if recent_dates:
        detail = (
            f"最近 {len(recent_dates)} 交易日內 ALERT [CRITICAL] {recent_critical} 筆"
            f"（全檔 {total_critical} 筆）"
        )
        return recent_critical, detail
    return total_critical, f"log 內 ALERT [CRITICAL] 共 {total_critical} 筆"


def evaluate_pilot_gate(
    report_paths: list[Path],
    *,
    log_file: Path | None = None,
    broker_csv: Path | None = None,
    tick_csv: Path | None = None,
    big_loss_threshold: float = BIG_LOSS_DAILY_PNL_POINTS,
) -> PilotGateResult:
    if not report_paths:
        return PilotGateResult(
            passed=False,
            checks=[
                GateCheck(
                    id="reports_present",
                    label="UAT JSON 報告存在",
                    passed=False,
                    detail="未提供任何 reports/day*.json",
                )
            ],
        )

    reports = load_metrics_from_json_paths(report_paths)
    trading_days = len(reports)
    report_dates = {date for date, _data in reports}
    recent_10_dates = {date for date, _data in reports[-10:]}
    total_rounds = sum(int(data.get("completed_rounds") or 0) for _d, data in reports)
    recent_10 = reports[-10:]
    recent_10_rounds = sum(
        int(data.get("completed_rounds") or 0) for _d, data in recent_10
    )
    zero_trade_days = sum(
        1 for _d, data in reports if int(data.get("completed_rounds") or 0) == 0
    )

    recent_exp_gross = _weighted_expectancy(recent_10, field_name="expectancy_per_trade_gross")
    recent_exp_net = _weighted_expectancy(recent_10, field_name="expectancy_per_trade_net")

    daily_pnls = daily_pnl_series(reports)
    daily_returns = [pnl for _d, pnl in daily_pnls]
    sharpe_daily_block = compute_sharpe_sortino(daily_returns, period="daily")
    sharpe_daily = sharpe_daily_block.get("sharpe")

    per_trade_returns = per_trade_return_series(reports)
    sharpe_trade_block = compute_sharpe_sortino(per_trade_returns, period="per_trade")
    sharpe_per_trade = sharpe_trade_block.get("sharpe")

    all_summaries: list[dict] = []
    seen_dates: set[str] = set()
    for date, data in reports:
        for summary in data.get("daily_summaries") or []:
            summary_date = str(summary.get("date") or date)
            if summary_date in seen_dates:
                continue
            seen_dates.add(summary_date)
            all_summaries.append(summary)

    max_acceptable_mdd: float | None = None
    initial_capital = 0.0
    for _date, data in reversed(reports):
        cum = data.get("cumulative_risk") or {}
        if max_acceptable_mdd is None and cum.get("max_acceptable_mdd_points") is not None:
            max_acceptable_mdd = float(cum["max_acceptable_mdd_points"])
        if initial_capital == 0.0 and cum.get("initial_capital_points"):
            initial_capital = float(cum["initial_capital_points"])
    if max_acceptable_mdd is None:
        try:
            from config import INITIAL_CAPITAL_POINTS, MAX_ACCEPTABLE_MDD_POINTS

            initial_capital = float(INITIAL_CAPITAL_POINTS)
            max_acceptable_mdd = float(MAX_ACCEPTABLE_MDD_POINTS)
        except Exception:
            max_acceptable_mdd = None

    cumulative_risk = compute_cumulative_risk_progression(
        all_summaries,
        initial_capital=initial_capital,
        max_acceptable_mdd=max_acceptable_mdd,
    )
    mdd_budget_pct = cumulative_risk.get("budget_used_pct")

    density_failures: list[str] = []
    for start in range(0, len(reports), DENSITY_WINDOW_DAYS):
        window = reports[start : start + DENSITY_WINDOW_DAYS]
        if len(window) < DENSITY_WINDOW_DAYS:
            continue
        window_rounds = sum(int(data.get("completed_rounds") or 0) for _d, data in window)
        if window_rounds < DENSITY_MIN_ROUND_TRIPS:
            density_failures.append(
                f"{window[0][0]}..{window[-1][0]}={window_rounds} 筆"
            )

    has_big_loss_streak, big_loss_detail = _has_consecutive_big_losses(
        daily_pnls,
        threshold=big_loss_threshold,
        streak=CONSECUTIVE_BIG_LOSS_DAYS,
    )

    critical_count, critical_detail = _count_critical_alerts(
        log_file,
        recent_dates=recent_10_dates,
    )

    broker_file_exists = broker_csv is not None and broker_csv.is_file()
    if broker_file_exists:
        broker_passed, broker_detail = evaluate_broker_reconciliation_csv(
            broker_csv,
            expected_dates=report_dates,
        )
    else:
        broker_passed = False
        broker_detail = f"尚未產出 {broker_csv}（先跑 reporting.uat_evidence_export broker）"

    tick_file_exists = tick_csv is not None and tick_csv.is_file()
    if tick_file_exists:
        tick_passed, tick_detail = evaluate_tick_stratification_csv(
            tick_csv,
            expected_dates=report_dates,
        )
    else:
        tick_passed = False
        tick_detail = f"尚未產出 {tick_csv}（先跑 reporting.uat_evidence_export tick）"

    sharpe_gate_value = sharpe_per_trade if sharpe_per_trade is not None else sharpe_daily
    sharpe_gate_label = "per_trade" if sharpe_per_trade is not None else "daily"

    checks: list[GateCheck] = [
        GateCheck(
            id="sample_trading_days",
            label=f"樣本 ≥ {MIN_TRADING_DAYS} 交易日",
            passed=trading_days >= MIN_TRADING_DAYS,
            detail=f"{trading_days} 日（0 成交日 {zero_trade_days} 日）",
        ),
        GateCheck(
            id="sample_round_trips_total",
            label=f"整體 ≥ {MIN_ROUND_TRIPS_TOTAL} round-trip",
            passed=total_rounds >= MIN_ROUND_TRIPS_TOTAL,
            detail=f"{total_rounds} 筆",
        ),
        GateCheck(
            id="sample_round_trips_recent_10",
            label=f"最近 10 日 ≥ {MIN_ROUND_TRIPS_RECENT_10} round-trip",
            passed=recent_10_rounds >= MIN_ROUND_TRIPS_RECENT_10,
            detail=f"{recent_10_rounds} 筆",
        ),
        GateCheck(
            id="density_5d_8rt",
            label=f"每 {DENSITY_WINDOW_DAYS} 日 ≥ {DENSITY_MIN_ROUND_TRIPS} round-trip",
            passed=not density_failures,
            detail="通過" if not density_failures else "未達：" + "; ".join(density_failures),
        ),
        GateCheck(
            id="expectancy_net_recent",
            label=f"最近窗 Expectancy (net) > {MIN_EXPECTANCY_NET_RECENT}",
            passed=recent_exp_net is not None and recent_exp_net > MIN_EXPECTANCY_NET_RECENT,
            detail=(
                f"net={recent_exp_net}, gross={recent_exp_gross}"
                if recent_exp_net is not None
                else "樣本不足（最近 10 日無 completed round-trip）"
            ),
        ),
        GateCheck(
            id="expectancy_net_health",
            label=f"最近 10 日 Expectancy (net) > {MIN_EXPECTANCY_NET_HEALTH}",
            passed=recent_exp_net is not None and recent_exp_net > MIN_EXPECTANCY_NET_HEALTH,
            detail=f"net={recent_exp_net}" if recent_exp_net is not None else "樣本不足",
        ),
        GateCheck(
            id="sharpe",
            label=f"Sharpe > {MIN_SHARPE}（gate={sharpe_gate_label}）",
            passed=sharpe_gate_value is not None and sharpe_gate_value > MIN_SHARPE,
            detail=(
                f"per_trade={sharpe_per_trade} (n={len(per_trade_returns)}) | "
                f"daily={sharpe_daily} (n={len(daily_returns)})"
            ),
        ),
        GateCheck(
            id="mdd_budget",
            label=f"MDD 使用率 < {MAX_MDD_BUDGET_PCT}%",
            passed=mdd_budget_pct is not None and mdd_budget_pct < MAX_MDD_BUDGET_PCT,
            detail=(
                f"{mdd_budget_pct}%"
                if mdd_budget_pct is not None
                else "未設定 max_acceptable_mdd_points 或無 daily_summaries"
            ),
        ),
        GateCheck(
            id="no_consecutive_big_loss",
            label=f"無連續 {CONSECUTIVE_BIG_LOSS_DAYS} 日大虧損",
            passed=not has_big_loss_streak,
            detail=big_loss_detail,
        ),
        GateCheck(
            id="zero_critical",
            label="零 Critical（最近 10 交易日 log 掃描）",
            passed=critical_count == 0 if critical_count is not None else False,
            detail=critical_detail,
            manual=critical_count is None,
        ),
        GateCheck(
            id="broker_reconciliation",
            label="摩擦對帳（券商 vs log CSV）",
            passed=broker_passed,
            detail=broker_detail,
            manual=not broker_file_exists,
        ),
        GateCheck(
            id="tick_stratification",
            label="Tick 品質分層觀測（CSV）",
            passed=tick_passed,
            detail=tick_detail,
            manual=not tick_file_exists,
        ),
        GateCheck(
            id="param_freeze",
            label="參數凍結 ≥ 10 交易日（git 證明）",
            passed=False,
            detail="需人工：git log snapshots/config_*.yaml",
            manual=True,
        ),
        GateCheck(
            id="stress_timelines",
            label="≥3 壓力情境 audit timeline（含 near-miss）人類審閱",
            passed=False,
            detail="需人工：uat_evidence/phase5_review/",
            manual=True,
        ),
        GateCheck(
            id="human_signoff",
            label="人類負責人簽核",
            passed=False,
            detail="APP.md Phase 5 審核表 + 前 5 大虧損日",
            manual=True,
        ),
    ]

    auto_checks = [c for c in checks if not c.manual]
    auto_passed = all(c.passed for c in auto_checks)
    summary = {
        "trading_days": trading_days,
        "zero_trade_days": zero_trade_days,
        "total_round_trips": total_rounds,
        "recent_10_round_trips": recent_10_rounds,
        "recent_expectancy_gross": recent_exp_gross,
        "recent_expectancy_net": recent_exp_net,
        "sharpe_per_trade": sharpe_per_trade,
        "sharpe_daily": sharpe_daily,
        "sharpe_gate_basis": sharpe_gate_label,
        "mdd_budget_used_pct": mdd_budget_pct,
        "auto_checks_passed": auto_passed,
        "auto_checks_total": len(auto_checks),
        "manual_checks_total": sum(1 for c in checks if c.manual),
    }

    return PilotGateResult(
        passed=auto_passed,
        checks=checks,
        summary=summary,
    )


def format_pilot_gate_report(result: PilotGateResult) -> str:
    lines = ["=== Pilot Readiness Gate (APP.md Phase 5) ==="]
    lines.append(
        f"自動檢查：{'PASS' if result.summary.get('auto_checks_passed') else 'FAIL'} "
        f"({sum(1 for c in result.checks if not c.manual and c.passed)}/"
        f"{result.summary.get('auto_checks_total')}）"
    )
    lines.append("")
    for check in result.checks:
        tag = "MANUAL" if check.manual else ("PASS" if check.passed else "FAIL")
        lines.append(f"[{tag}] {check.label}")
        lines.append(f"       {check.detail}")
    lines.append("")
    verdict = "Go（自動項通過；仍需人工簽核）" if result.passed else "No-Go（自動項未達標）"
    lines.append(f"結論：{verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    default_broker = DEFAULT_UAT_EVIDENCE_DIR / "phase3_weekly" / "broker_reconciliation.csv"
    default_tick = DEFAULT_UAT_EVIDENCE_DIR / "phase4_stress" / "tick_quality_stratification.csv"

    parser = argparse.ArgumentParser(
        description="Evaluate APP.md Phase 5 Pilot Readiness Gate from saved UAT JSON reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m sweep.pilot_gate_check reports\\day*.json\n"
            "  python -m sweep.pilot_gate_check reports\\day*.json --log-file C:\\logs\\trading-app-uat.log\n"
            "  python -m sweep.pilot_gate_check reports\\day*.json --json\n"
            "  python -m sweep.pilot_gate_check reports\\day*.json "
            "--broker-csv uat_evidence\\phase3_weekly\\broker_reconciliation.csv\n"
            "\n"
            "Sharpe gate uses per-trade returns when available, else daily PnL.\n"
            "Broker/tick CSV checks are MANUAL until files exist (run uat_evidence_export first).\n"
        ),
    )
    parser.add_argument(
        "report_files",
        nargs="+",
        type=Path,
        help="reports/day*.json from `python -m reporting <log> --json`",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional strategy log for ALERT [CRITICAL] scan (recent 10 trading days)",
    )
    parser.add_argument(
        "--broker-csv",
        type=Path,
        default=default_broker,
        help=f"Broker reconciliation CSV (default: {default_broker})",
    )
    parser.add_argument(
        "--tick-csv",
        type=Path,
        default=default_tick,
        help=f"Tick stratification CSV (default: {default_tick})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON",
    )
    parser.add_argument(
        "--big-loss-threshold",
        type=float,
        default=BIG_LOSS_DAILY_PNL_POINTS,
        help=f"Daily PnL (points) threshold for consecutive loss streak (default: {BIG_LOSS_DAILY_PNL_POINTS})",
    )
    args = parser.parse_args(argv)

    for path in args.report_files:
        if not path.is_file():
            print(f"找不到檔案: {path}", file=sys.stderr)
            return 1

    result = evaluate_pilot_gate(
        args.report_files,
        log_file=args.log_file,
        broker_csv=args.broker_csv,
        tick_csv=args.tick_csv,
        big_loss_threshold=args.big_loss_threshold,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_pilot_gate_report(result))

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())