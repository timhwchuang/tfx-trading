"""Tests for FT-003 entry funnel replay and aggregation."""

from __future__ import annotations

import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from reporting.entry_funnel import (
    EntryFunnelConfig,
    armed_forward_window_stats,
    classify_episode_outcome,
    episode_end_ts,
    replay_episode_funnel,
    _filter_daily_summaries_by_date,
    _tick_rows_for_day,
)
from reporting.forward_pnl import TickSeries
from reporting.structure_calibration import ArmedCandidate
from reporting.uat_report import Episode, compute_episodes


class TestEntryFunnelReplay(unittest.TestCase):
    def test_replay_near_vwap_and_vol_dried(self):
        cfg = EntryFunnelConfig(
            entry_band_points=5.0,
            momentum_vol_1s=150,
            exhaustion_vol=15,
            momentum_timeout_sec=180,
            vwap_window_min=5,
        )
        armed_ts = 1000
        ticks = [
            (armed_ts - 60, 100.0, 10, 1),
            (armed_ts, 100.0, 200, 1),
            (armed_ts + 1, 100.0, 1, 1),
            (armed_ts + 2, 101.0, 1, 1),
        ]
        stats = replay_episode_funnel(
            ticks,
            armed_ts=armed_ts,
            end_ts=armed_ts + 10,
            trigger_price=100.0,
            direction="Long",
            cfg=cfg,
            vol_at_arm_audit=200,
            entry_ts=None,
        )
        self.assertTrue(stats.ever_near_vwap)
        self.assertTrue(stats.ever_vol_dried)
        self.assertTrue(stats.both_same_tick)

    def test_armed_forward_close_delta_long(self):
        series = TickSeries(
            timestamps=[100, 110, 120, 130],
            closes=[100.0, 105.0, 103.0, 108.0],
        )
        armed = ArmedCandidate(
            episode_id="e1",
            ts=100,
            direction="Long",
            price=100.0,
            atr=10.0,
        )
        w30 = armed_forward_window_stats(armed, series, 30, atr=10.0)
        self.assertEqual(w30["close_delta"], 8.0)
        self.assertGreater(w30["MFE_delta"], 0)

    def test_classify_veto_subtype(self):
        ep = Episode(
            episode_id="x",
            outcome="veto",
            events=[{"event_type": "structure_veto", "ts": 1}],
        )
        self.assertEqual(classify_episode_outcome(ep), "structure_veto")

    def test_episode_end_ts_caps_at_timeout(self):
        cfg = EntryFunnelConfig(2.0, 150, 15, 180)
        ep = Episode(
            episode_id="20260401-001",
            armed_ts=1000,
            outcome="timeout",
            events=[
                {"event_type": "momentum_armed", "ts": 1000},
                {"event_type": "momentum_timeout", "ts": 1100},
            ],
        )
        armed, end, entry = episode_end_ts(ep, cfg)
        self.assertEqual(armed, 1000)
        self.assertEqual(end, 1100)
        self.assertIsNone(entry)

    def test_episode_end_ts_caps_at_veto(self):
        cfg = EntryFunnelConfig(2.0, 150, 15, 180)
        ep = Episode(
            episode_id="20260401-002",
            armed_ts=1000,
            outcome="veto",
            events=[
                {"event_type": "momentum_armed", "ts": 1000},
                {"event_type": "trend_veto", "ts": 1050},
            ],
        )
        _, end, _ = episode_end_ts(ep, cfg)
        self.assertEqual(end, 1050)

    def test_classify_entered_before_risk_blocked(self):
        ep = Episode(
            episode_id="x",
            outcome="risk_blocked",
            events=[
                {"source": "signal", "event_type": "entry", "ts": 1050},
                {"event_type": "risk_blocked", "ts": 1060},
            ],
        )
        self.assertEqual(classify_episode_outcome(ep), "entered")

    def test_filter_daily_summaries_by_date(self):
        daily = [
            {"date": "2026-04-01", "near_miss": {"blocked_both": 1}},
            {"date": "2026-04-15", "near_miss": {"blocked_both": 2}},
            {"date": "2026-05-01", "near_miss": {"blocked_both": 99}},
        ]
        filtered = _filter_daily_summaries_by_date(daily, "2026-04-01", "2026-04-30")
        self.assertEqual([d["date"] for d in filtered], ["2026-04-01", "2026-04-15"])

    def test_compute_episodes_armed_to_entry(self):
        lines = [
            'DECISION_AUDIT {"audit_schema_version":1,"event_type":"momentum_armed","ts":1000,"episode_id":"20260401-001","direction":"Long","trigger_price":100.0,"vol_1s":160,"buy_ratio":0.85}',
            'SIGNAL_AUDIT {"audit_schema_version":1,"intent":"entry","direction":"Buy","price":100.0,"ts":1050,"episode_id":"20260401-001","signal_id":"sig-1"}',
            'FILL_AUDIT {"intent":"entry","direction":"Buy","signal_price":100.0,"fill_price":100.0,"slippage_pts":0.0,"limit_price":100.0,"slippage_vs_limit_pts":0.0,"order_id":"1","ts":1051,"episode_id":"20260401-001","signal_id":"sig-1"}',
        ]
        eps = compute_episodes(lines)
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].outcome, "entered")


class TestEntryFunnelTickCache(unittest.TestCase):
    def test_replay_with_csv_ticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            p = cache / "TMFR1_2026-04-01.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["datetime", "close", "volume", "bid_price", "ask_price", "tick_type"])
                base = "2026-04-01T09:00:00"
                w.writerow([f"{base}+00:00", 100.0, 50, 99, 101, 1])
                w.writerow(["2026-04-01T09:00:01+00:00", 100.0, 1, 99, 101, 1])
                w.writerow(["2026-04-01T09:00:02+00:00", 100.5, 1, 99, 101, 1])

            rows = _tick_rows_for_day("TMFR1", dt.date(2026, 4, 1), cache_dir=cache)
            self.assertGreaterEqual(len(rows), 2)
            cfg = EntryFunnelConfig(2.0, 150, 15, 180)
            armed_ts = rows[0][0]
            stats = replay_episode_funnel(
                rows,
                armed_ts=armed_ts,
                end_ts=armed_ts + 5,
                trigger_price=100.0,
                direction="Long",
                cfg=cfg,
                vol_at_arm_audit=50,
                entry_ts=None,
            )
            self.assertIsNotNone(stats.closest_vwap_distance)


if __name__ == "__main__":
    unittest.main()
