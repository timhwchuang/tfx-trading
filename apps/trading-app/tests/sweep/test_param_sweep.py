"""Phase 5 + 6.6: Parameter sweep and config patch tests."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from core.runtime_config import default_runtime_config
from tests.sweep._tick_helpers import make_replay_tick
from observability import build_config_snapshot
from sweep.param_sweep import (
    _apply_params,
    _capture_prefixes_for_params,
    _partition_combos,
    _restore_params,
    _run_backtest_summaries,
    sweep,
    validate_sweep_inputs,
)
from sweep.sweep_progress import SweepProgressTracker
from integrations.engine_wiring import trading_app_engine_ports
from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy
from trading_engine.engine import TradingEngine


class TestParamSweep(unittest.TestCase):
    def test_sweep_small_grid(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "ENTRY_BAND_POINTS": [2.0, 3.0],
            "VWAP_STOP_POINTS": [3, 4],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                results = sweep(
                    grid,
                    dates_train=[datetime.date(2026, 6, 12)],
                    dates_valid=[datetime.date(2026, 6, 13)],
                    code="TXFR1",
                    cache_dir=cache_dir,
                )
        self.assertEqual(len(results), 4)
        for row in results:
            self.assertIn("params", row)
            self.assertIn("train_kpi", row)
            self.assertIn("valid_kpi", row)
        scores = [r["valid_score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_sweep_with_trend_params_attaches_veto_metrics(self):
        """P6-1-CAL-3: param_sweep now accepts trend_ keys and attaches veto_metrics via harness."""
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "trend_filter_enabled": [False, True],
            "trend_min_strength": [0.0, 0.5],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                results = sweep(
                    grid,
                    dates_train=[datetime.date(2026, 6, 12)],
                    dates_valid=[datetime.date(2026, 6, 13)],
                    code="TXFR1",
                    cache_dir=cache_dir,
                )
        self.assertEqual(len(results), 4)
        for row in results:
            self.assertIn("params", row)
            self.assertIn("veto_metrics", row)
            self.assertIn("veto_rate", row["veto_metrics"])

    def test_config_restored(self):
        cfg = default_runtime_config()
        original_cfg = cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points)
        saved = _apply_params({"ENTRY_BAND_POINTS": 99.0}, cfg)
        _restore_params(saved, cfg)
        self.assertEqual(
            cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
            original_cfg,
        )

    def test_daily_summary_params_match_sweep(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        cfg = default_runtime_config()
        saved = _apply_params({"ENTRY_BAND_POINTS": 42.0}, cfg)
        try:
            self.assertEqual(
                build_config_snapshot(cfg)["entry_band_points"], 42.0
            )
            with tempfile.TemporaryDirectory() as tmp:
                cache_dir = Path(tmp)
                with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                    summaries, _signals, _decisions = _run_backtest_summaries(
                        "TXFR1",
                        [datetime.date(2026, 6, 12)],
                        cache_dir,
                        runtime_config=cfg,
                    )
            self.assertEqual(
                summaries[-1]["params"]["entry_band_points"],
                42.0,
            )
        finally:
            _restore_params(saved, cfg)

    def test_sweep_params_affect_entry(self):
        cfg = default_runtime_config()
        original = cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points)
        saved = _apply_params({"ENTRY_BAND_POINTS": 7.5}, cfg)
        try:
            api = MagicMock()
            ports = trading_app_engine_ports(
                api=api, use_mock_adapter=True, runtime_config=cfg
            )
            host = TradingEngine(
                api=api,
                strategy=VWAPMomentumStrategy(
                    params=StrategyParams.from_runtime_config(cfg),
                    obs=ports["obs"],
                ),
                **{k: v for k, v in ports.items() if k != "obs"},
            )
            host._api_connected = True
            host.current_vwap = 18000.0
            host.vol_1s = 1
            strat = host.strategy
            strat.momentum.active = True
            strat.momentum.direction = "Long"
            strat.momentum.trigger_time = 900
            host.current_atr = 30.0
            host.indicators.last_atr_refresh = 1000.0
            host.position_qty = 0
            host.is_pending = False
            host.consecutive_loss = 0
            host.last_exit_time = 0
            dt = datetime.datetime(2026, 6, 12, 10, 0, 0)
            self.assertEqual(
                cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
                7.5,
            )
            signal = host.process_strategy(1000, 18000.0, dt)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.intent, "entry")
        finally:
            _restore_params(saved, cfg)
        self.assertEqual(
            cfg.live_get("ENTRY_BAND_POINTS", cfg.entry_band_points),
            original,
        )


    def test_sweep_skips_mutually_exclusive_regime_combo(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "structure_filter_enabled": [True],
            "trend_filter_enabled": [True],
            "entry_band_points": [2.0],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                with self.assertLogs("sweep.param_sweep", level="WARNING") as cap:
                    results = sweep(
                        grid,
                        dates_train=[datetime.date(2026, 6, 12)],
                        dates_valid=[datetime.date(2026, 6, 13)],
                        code="TXFR1",
                        cache_dir=cache_dir,
                    )
        self.assertEqual(len(results), 0)
        self.assertTrue(
            any("skip mutually exclusive regime combo" in line for line in cap.output)
        )

    def test_sweep_regime_skip_emits_combo_skipped_progress(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "structure_filter_enabled": [True],
            "trend_filter_enabled": [True],
            "entry_band_points": [2.0],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            cache_dir.mkdir()
            progress_path = root / "sweep_progress.log"
            result_path = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress_path, result_path, heartbeat_sec=3600)
            tracker.start_sweep(agent="agent-regime-test")
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                results = sweep(
                    grid,
                    dates_train=[datetime.date(2026, 6, 12)],
                    dates_valid=[datetime.date(2026, 6, 13)],
                    code="TXFR1",
                    cache_dir=cache_dir,
                    progress=tracker,
                )
            tracker.finish("DONE", exit_code=0)
            self.assertEqual(len(results), 0)
            events = [
                json.loads(line)
                for line in progress_path.read_text(encoding="utf-8").strip().splitlines()
            ]
            skipped = [e for e in events if e["event"] == "combo_skipped"]
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["combo_index"], 1)
            self.assertNotIn("combo_start", {e["event"] for e in events})
            self.assertEqual(events[-1]["combos_skipped"], 1)
            self.assertEqual(events[-1]["combos_completed"], 0)

    def test_run_backtest_summaries_progress_defaults_to_bulk(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            progress_path = Path(tmp) / "sweep_progress.log"
            result_path = Path(tmp) / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress_path, result_path, heartbeat_sec=3600)
            tracker.start_sweep(agent="test")
            tracker.combo_start(
                1, 1, {"entry_band_points": 2.0},
                run_index=1, run_total=1, train_days=1, valid_days=1,
            )
            with patch("sweep.param_sweep._run_with_audit_capture", return_value=[]):
                _run_backtest_summaries(
                    "TXFR1",
                    [datetime.date(2026, 6, 12)],
                    cache_dir,
                    progress=tracker,
                    phase="train",
                )
            events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").strip().splitlines()]
            self.assertIn("phase_start", {e["event"] for e in events})
            self.assertNotIn("day", {e["event"] for e in events})

    def test_run_backtest_summaries_day_split_emits_progress(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            cache_dir.mkdir()
            progress_path = root / "sweep_progress.log"
            result_path = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress_path, result_path, heartbeat_sec=3600)
            tracker.start_sweep(agent="test")
            tracker.combo_start(
                1,
                1,
                {"entry_band_points": 2.0},
                run_index=1,
                run_total=1,
                train_days=2,
                valid_days=1,
            )
            dates = [datetime.date(2026, 6, 12), datetime.date(2026, 6, 13)]
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                _run_backtest_summaries(
                    "TXFR1",
                    dates,
                    cache_dir,
                    progress=tracker,
                    phase="train",
                    capture_prefixes=_capture_prefixes_for_params({"entry_band_points": 2.0}),
                    bulk_days=False,
                )
            events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").strip().splitlines()]
            day_events = [e for e in events if e["event"] == "day"]
            self.assertEqual(len(day_events), 2)
            self.assertEqual(day_events[0]["day_index"], 1)
            self.assertEqual(day_events[1]["day_index"], 2)

    def test_run_backtest_summaries_passes_daily_summary_capture_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            prefixes = _capture_prefixes_for_params({"entry_band_points": 2.0})
            with patch("sweep.param_sweep._run_with_audit_capture") as mock_capture:
                mock_capture.return_value = []
                _run_backtest_summaries(
                    "TXFR1",
                    [datetime.date(2026, 6, 12)],
                    cache_dir,
                    capture_prefixes=prefixes,
                )
            mock_capture.assert_called_once()
            self.assertEqual(mock_capture.call_args.kwargs["capture_prefixes"], prefixes)
            self.assertEqual(prefixes, ("DAILY_SUMMARY ",))

    def test_partition_combos_splits_regime_conflict(self):
        keys = ["structure_filter_enabled", "trend_filter_enabled", "entry_band_points"]
        combos = list(__import__("itertools").product([True], [True], [2.0]))
        runnable, skipped = _partition_combos(keys, combos)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(len(runnable), 0)

    def test_sweep_with_structure_params_attaches_structure_veto_metrics(self):
        ticks = [make_replay_tick(datetime.datetime(2026, 6, 12, 9, 0, 0))]

        def fake_replay(_code, _dates, cache_dir=None):
            yield from ticks

        grid = {
            "structure_min_strength": [0.0, 0.5],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with patch("trading_backtest.loader.iter_replay_ticks", fake_replay):
                results = sweep(
                    grid,
                    dates_train=[datetime.date(2026, 6, 12)],
                    dates_valid=[datetime.date(2026, 6, 13)],
                    code="TXFR1",
                    cache_dir=cache_dir,
                )
        self.assertEqual(len(results), 2)
        for row in results:
            self.assertIn("structure_veto_metrics", row)
            self.assertNotIn("veto_metrics", row)

    def test_min_atr_threshold_overlay_affects_strategy_params(self):
        cfg = default_runtime_config()
        saved = _apply_params({"min_atr_threshold": 36.0}, cfg)
        try:
            params = StrategyParams.from_runtime_config(cfg)
            self.assertEqual(params.min_atr_threshold, 36.0)
        finally:
            _restore_params(saved, cfg)

    def test_ioc_slippage_overlay_affects_cfg_getattr(self):
        cfg = default_runtime_config()
        original = cfg.ioc_slippage_points
        saved = _apply_params({"ioc_slippage_points": 5}, cfg)
        try:
            self.assertEqual(cfg.ioc_slippage_points, 5)
        finally:
            _restore_params(saved, cfg)
        self.assertEqual(cfg.ioc_slippage_points, original)


    def test_sweep_rejects_holdout_dates(self):
        grid = {"entry_band_points": [2.0]}
        with self.assertRaises(RuntimeError) as ctx:
            sweep(
                grid,
                dates_train=[datetime.date(2026, 5, 1)],
                dates_valid=[datetime.date(2026, 4, 1)],
                code="TXFR1",
                cache_dir=Path("/tmp"),
            )
        self.assertIn("holdout dates sealed", str(ctx.exception))

    def test_sweep_rejects_oversized_grid(self):
        grid = {f"k{i}": [1, 2, 3] for i in range(5)}  # 3^5 = 243 combos, 5 keys
        with self.assertRaises(ValueError) as ctx:
            sweep(
                grid,
                dates_train=[datetime.date(2026, 3, 2)],
                dates_valid=[datetime.date(2026, 4, 1)],
                code="TXFR1",
                cache_dir=Path("/tmp"),
            )
        self.assertIn("max", str(ctx.exception))

    def test_validate_sweep_inputs_rejects_holdout(self):
        grid = {"entry_band_points": [2.0]}
        with self.assertRaises(RuntimeError) as ctx:
            validate_sweep_inputs(
                grid,
                dates_train=[datetime.date(2026, 5, 1)],
                dates_valid=[datetime.date(2026, 4, 1)],
            )
        self.assertIn("holdout dates sealed", str(ctx.exception))

    def test_capture_prefixes_conservative_grid(self):
        prefixes = _capture_prefixes_for_params(
            {"entry_band_points": 2.0, "min_atr_threshold": 1.0}
        )
        self.assertEqual(prefixes, ("DAILY_SUMMARY ",))

    def test_capture_prefixes_trend_grid_includes_signal(self):
        prefixes = _capture_prefixes_for_params({"trend_filter_enabled": True})
        self.assertEqual(prefixes, ("DAILY_SUMMARY ", "SIGNAL_AUDIT "))

    def test_capture_prefixes_structure_grid_includes_decision(self):
        prefixes = _capture_prefixes_for_params({"structure_min_strength": 0.5})
        self.assertEqual(prefixes, ("DAILY_SUMMARY ", "DECISION_AUDIT "))

    def test_capture_prefixes_does_not_match_entry_trend_substring(self):
        prefixes = _capture_prefixes_for_params({"my_trend_proxy": 1.0})
        self.assertEqual(prefixes, ("DAILY_SUMMARY ",))


if __name__ == "__main__":
    unittest.main()