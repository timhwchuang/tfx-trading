"""Tests for sweep.pilot_gate_check (APP.md Phase 5)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sweep.pilot_gate_check import evaluate_pilot_gate


def _day_report(
    date: str,
    *,
    rounds: int,
    exp_net: float,
    exp_gross: float,
    daily_pnl: float,
    sharpe: float | None = 0.8,
    mdd_budget_pct: float = 30.0,
) -> dict:
    return {
        "completed_rounds": rounds,
        "performance": {
            "expectancy": {
                "expectancy_per_trade_gross": exp_gross,
                "expectancy_per_trade_net": exp_net,
            },
            "risk_adjusted": {"sharpe": sharpe},
            "total_pnl_net": daily_pnl,
        },
        "cumulative_risk": {
            "budget_used_pct": mdd_budget_pct,
            "max_acceptable_mdd_points": 200.0,
            "initial_capital_points": 0.0,
        },
        "daily_summaries": [
            {
                "date": date,
                "pnl": {"daily_pnl_points": daily_pnl},
                "performance": {"total_pnl_net": daily_pnl},
            }
        ],
    }


class TestPilotGateCheck(unittest.TestCase):
    def test_fails_with_insufficient_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "day20260601.json"
            path.write_text(
                json.dumps(_day_report("2026-06-01", rounds=4, exp_net=0.5, exp_gross=0.6, daily_pnl=2.0)),
                encoding="utf-8",
            )
            result = evaluate_pilot_gate([path])
            self.assertFalse(result.passed)
            sample = next(c for c in result.checks if c.id == "sample_trading_days")
            self.assertFalse(sample.passed)

    def test_passes_auto_checks_with_synthetic_20_day_sample(self):
        reports: list[Path] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for i in range(20):
                day = f"2026-06-{i + 1:02d}"
                path = tmp_path / f"day202606{i + 1:02d}.json"
                daily_pnl = 1.0 + (i % 5) * 0.3
                path.write_text(
                    json.dumps(
                        _day_report(
                            day,
                            rounds=4,
                            exp_net=0.40,
                            exp_gross=0.45,
                            daily_pnl=daily_pnl,
                            mdd_budget_pct=20.0 + i * 0.5,
                        )
                    ),
                    encoding="utf-8",
                )
                reports.append(path)

            result = evaluate_pilot_gate(reports)
            auto = [c for c in result.checks if not c.manual]
            self.assertTrue(all(c.passed for c in auto), [c for c in auto if not c.passed])
            self.assertTrue(result.passed)

    def test_detects_consecutive_big_loss_streak(self):
        reports: list[Path] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pnls = [2.0, -25.0, -30.0, -22.0, 1.0]
            for i, pnl in enumerate(pnls):
                day = f"2026-06-{i + 1:02d}"
                path = tmp_path / f"day202606{i + 1:02d}.json"
                path.write_text(
                    json.dumps(
                        _day_report(
                            day,
                            rounds=20,
                            exp_net=0.4,
                            exp_gross=0.45,
                            daily_pnl=pnl,
                        )
                    ),
                    encoding="utf-8",
                )
                reports.append(path)

            result = evaluate_pilot_gate(reports, big_loss_threshold=-20.0)
            streak = next(c for c in result.checks if c.id == "no_consecutive_big_loss")
            self.assertFalse(streak.passed)

    def test_critical_scan_from_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "day20260601.json"
            report.write_text(
                json.dumps(_day_report("2026-06-01", rounds=80, exp_net=0.5, exp_gross=0.55, daily_pnl=3.0)),
                encoding="utf-8",
            )
            log_path = tmp_path / "uat.log"
            log_path.write_text(
                "2026-06-01 10:00:00 [CRITICAL] ALERT [CRITICAL] Pending 超時\n",
                encoding="utf-8",
            )
            result = evaluate_pilot_gate([report], log_file=log_path)
            critical = next(c for c in result.checks if c.id == "zero_critical")
            self.assertFalse(critical.passed)

    def test_reads_broker_and_tick_csv_when_present(self):
        reports: list[Path] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for i in range(20):
                day = f"2026-06-{i + 1:02d}"
                path = tmp_path / f"day202606{i + 1:02d}.json"
                path.write_text(
                    json.dumps(
                        _day_report(
                            day,
                            rounds=4,
                            exp_net=0.40 + (i % 3) * 0.05,
                            exp_gross=0.45,
                            daily_pnl=1.5 + (i % 4) * 0.2,
                        )
                    ),
                    encoding="utf-8",
                )
                reports.append(path)

            broker_csv = tmp_path / "broker.csv"
            broker_csv.write_text(
                "date,broker_daily_pnl_pts,log_daily_pnl_points,diff_pts,round_trips,broker_source_note,explained_y_or_n,explanation\n"
                + "\n".join(
                    f"2026-06-{i + 1:02d},{1.5},{1.5},0.00,4,sim,Y,ok"
                    for i in range(20)
                )
                + "\n",
                encoding="utf-8",
            )
            tick_csv = tmp_path / "tick.csv"
            tick_csv.write_text(
                "date,type0_pct,tier,signal_intents,fills,conversion_pct,expectancy_gross_pts,expectancy_net_pts,notes\n"
                + "\n".join(
                    f"2026-06-{i + 1:02d},25.0,low_lt30,4,4,80.00,0.45,0.40,"
                    for i in range(20)
                )
                + "\n",
                encoding="utf-8",
            )

            result = evaluate_pilot_gate(
                reports,
                broker_csv=broker_csv,
                tick_csv=tick_csv,
            )
            broker = next(c for c in result.checks if c.id == "broker_reconciliation")
            tick = next(c for c in result.checks if c.id == "tick_stratification")
            self.assertTrue(broker.passed, broker.detail)
            self.assertTrue(tick.passed, tick.detail)
            self.assertIn(result.summary.get("sharpe_gate_basis"), ("per_trade", "daily"))
            self.assertTrue(
                result.summary.get("sharpe_per_trade") is not None
                or result.summary.get("sharpe_daily") is not None
            )


if __name__ == "__main__":
    unittest.main()