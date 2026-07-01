"""Tests for GUDT live staged bootstrap (FT-022 Phase 4)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.gudt_live_bootstrap import (
    GudtLiveBootstrapCoordinator,
    attach_gudt_live_coordinator,
    start_live_session,
)
from reporting.gudt_wash_probe import DayWashContext
from strategy_gudt_route_a import GudtRouteAParams, GudtRouteAStrategy
from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestApplyIntradayPlan(unittest.TestCase):
    def _strategy(self) -> GudtRouteAStrategy:
        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config()))
        return GudtRouteAStrategy(params=GudtRouteAParams.from_runtime_config(cfg))

    def test_apply_intraday_plan_reloads_pending_events(self) -> None:
        strategy = self._strategy()
        strategy._current_day = "2026-06-03"
        strategy._plan = DayReplayPlan(day="2026-06-03", path="skip", skipped=True)
        strategy._event_idx = 5
        plan = DayReplayPlan(
            day="2026-06-03",
            path="p0+sealed",
            events=[
                TradeEvent(
                    ts=1_000,
                    action="Buy",
                    price=100.0,
                    leg="long_entry",
                    reason="p0+sealed",
                )
            ],
            skipped=False,
        )
        strategy.apply_intraday_plan("2026-06-03", plan)
        self.assertEqual(strategy._plan, plan)
        self.assertEqual(strategy._event_idx, 0)
        self.assertEqual(len(strategy._pending_events), 1)
        self.assertEqual(strategy._day_plans["2026-06-03"], plan)

    def test_apply_intraday_plan_skips_past_events_live(self) -> None:
        strategy = self._strategy()
        strategy._current_day = "2026-06-03"
        plan = DayReplayPlan(
            day="2026-06-03",
            path="p0+sealed",
            events=[
                TradeEvent(
                    ts=1_000,
                    action="Buy",
                    price=100.0,
                    leg="long_entry",
                    reason="stale",
                ),
                TradeEvent(
                    ts=5_000,
                    action="Buy",
                    price=101.0,
                    leg="long_entry",
                    reason="future",
                ),
            ],
            skipped=False,
        )
        strategy.apply_intraday_plan("2026-06-03", plan, as_of_ts=3_000)
        self.assertEqual(len(strategy._pending_events), 1)
        self.assertEqual(strategy._pending_events[0].ts, 5_000)

    def test_apply_intraday_plan_other_day_stores_only(self) -> None:
        strategy = self._strategy()
        strategy._current_day = "2026-06-03"
        plan = DayReplayPlan(day="2026-06-04", path="p0", skipped=False, events=[])
        strategy.apply_intraday_plan("2026-06-04", plan)
        self.assertEqual(strategy._day_plans["2026-06-04"], plan)
        self.assertIsNone(strategy._plan)


class TestGudtLiveBootstrapCoordinator(unittest.TestCase):
    def _strategy_and_cfg(self) -> tuple[GudtRouteAStrategy, TradingAppRuntimeConfig]:
        path = REPO_ROOT / "workspaces/gudt-route-a-baseline/config/config.yaml"
        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config(path)))
        return GudtRouteAStrategy(params=GudtRouteAParams.from_runtime_config(cfg)), cfg

    def test_start_empty_cache_terminal_no_prior_close(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            with mock.patch(
                "integrations.gudt_live_bootstrap.resolve_cli_tick_cache_dates",
                side_effect=ValueError("no cache"),
            ):
                coord.start()
            self.assertTrue(coord.terminal)
            self.assertEqual(coord.state, "NotGudtDay")

    def test_start_prior_close_without_today_tick_file(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            with mock.patch(
                "integrations.gudt_live_bootstrap.resolve_cli_tick_cache_dates",
                return_value=[datetime.date(2026, 6, 2)],
            ):
                with mock.patch(
                    "integrations.gudt_live_bootstrap._prior_close",
                    return_value=100.0,
                ):
                    coord.start()
            self.assertFalse(coord.terminal)
            self.assertEqual(coord.state, "AwaitingOpen")
            self.assertEqual(coord._prior_close, 100.0)

    def test_start_no_prior_close_terminal(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            with mock.patch(
                "integrations.gudt_live_bootstrap.resolve_cli_tick_cache_dates",
                return_value=[datetime.date(2026, 6, 3)],
            ):
                with mock.patch(
                    "integrations.gudt_live_bootstrap._prior_session_date",
                    return_value=None,
                ):
                    coord.start()
            self.assertTrue(coord.terminal)
            self.assertEqual(coord.state, "NotGudtDay")

    def test_awaiting_open_waits_for_kbar_until_atr_window(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._prior_close = 100.0
            coord._state = "AwaitingOpen"
            with mock.patch.object(coord, "_load_today_bars", return_value=[]):
                coord._step(datetime.datetime(2026, 6, 3, 8, 50))
            self.assertFalse(coord.terminal)
            self.assertEqual(coord.state, "AwaitingOpen")

    def test_awaiting_open_to_atr(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._prior_close = 100.0
            coord._state = "AwaitingOpen"
            with mock.patch.object(coord, "_load_today_bars", return_value=[mock.MagicMock()]):
                with mock.patch(
                    "integrations.gudt_live_bootstrap._open_0845",
                    return_value=108.0,
                ):
                    coord._step(datetime.datetime(2026, 6, 3, 8, 46))
            self.assertEqual(coord.state, "AwaitingAtr")

    def test_awaiting_atr_throttle(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._state = "AwaitingAtr"
            coord._last_awaiting_atr_log_mono = 0.0
            with mock.patch(
                "integrations.gudt_live_bootstrap.time.monotonic",
                side_effect=[100.0, 399.0],
            ):
                with self.assertLogs("integrations.gudt_live_bootstrap", level="INFO") as logs:
                    coord._maybe_log_awaiting_atr()
                    coord._maybe_log_awaiting_atr()
            awaiting_logs = [m for m in logs.output if "awaiting_atr" in m]
            self.assertEqual(len(awaiting_logs), 1)

    def test_not_gudt_day_after_qualify_fail(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._state = "AwaitingAtr"
            with mock.patch(
                "integrations.gudt_live_bootstrap.load_probe_contexts",
                return_value={},
            ):
                coord._step(datetime.datetime(2026, 6, 3, 9, 15))
            self.assertTrue(coord.terminal)
            self.assertEqual(coord.state, "NotGudtDay")

    def test_plan_ready_applies_intraday_plan(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._state = "AwaitingSignal"
            plan = DayReplayPlan(
                day="2026-06-03",
                path="p0+sealed",
                events=[
                    TradeEvent(
                        ts=1,
                        action="Buy",
                        price=100.0,
                        leg="long_entry",
                        reason="p0",
                    )
                ],
                skipped=False,
            )
            with mock.patch.object(coord, "_sorted_dates", return_value=[datetime.date(2026, 6, 3)]):
                with mock.patch(
                    "integrations.gudt_live_bootstrap.probe_day_rows",
                    return_value=[{"day": "2026-06-03", "path": "p0"}],
                ):
                    with mock.patch(
                        "integrations.gudt_live_bootstrap.load_probe_contexts",
                        return_value={
                            "2026-06-03": DayWashContext(
                                day=datetime.date(2026, 6, 3),
                                atr=30.0,
                                drive_high=110.0,
                                drive_low=90.0,
                                gap_pts=8.0,
                                open_0845=108.0,
                                prior_close=100.0,
                                ticks=[],
                            )
                        },
                    ):
                        with mock.patch(
                            "integrations.gudt_live_bootstrap.build_replay_plans_for_range",
                            return_value={"2026-06-03": plan},
                        ):
                            coord._try_build_plan()
            self.assertEqual(coord.state, "PlanReady")
            self.assertTrue(coord.terminal)
            self.assertEqual(strategy._day_plans["2026-06-03"], plan)

    def test_router_skip_terminal(self) -> None:
        strategy, cfg = self._strategy_and_cfg()
        with tempfile.TemporaryDirectory() as d:
            coord = GudtLiveBootstrapCoordinator(
                strategy=strategy,
                cfg=cfg,
                code="TMFR1",
                cache_dir=Path(d),
                trade_day=datetime.date(2026, 6, 3),
            )
            coord._state = "AwaitingSignal"
            skip_plan = DayReplayPlan(day="2026-06-03", path="skip", skipped=True)
            with mock.patch.object(coord, "_sorted_dates", return_value=[datetime.date(2026, 6, 3)]):
                with mock.patch(
                    "integrations.gudt_live_bootstrap.probe_day_rows",
                    return_value=[{"day": "2026-06-03"}],
                ):
                    with mock.patch(
                        "integrations.gudt_live_bootstrap.load_probe_contexts",
                        return_value={},
                    ):
                        with mock.patch(
                            "integrations.gudt_live_bootstrap.build_replay_plans_for_range",
                            return_value={"2026-06-03": skip_plan},
                        ):
                            coord._try_build_plan()
            self.assertEqual(coord.state, "RouterSkip")
            self.assertTrue(coord.terminal)


class TestLiveWiring(unittest.TestCase):
    def test_attach_non_gudt_returns_none(self) -> None:
        from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy

        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config()))
        strat = VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))
        out = attach_gudt_live_coordinator(
            strat,
            cfg,
            code="TMFR1",
            cache_dir=REPO_ROOT / "tick_cache",
        )
        self.assertIsNone(out)

    def test_start_live_session_wires_coordinator(self) -> None:
        engine = mock.MagicMock()
        coord = mock.MagicMock()
        boot = mock.MagicMock()

        with mock.patch(
            "trading_engine.adapters.shioaji_live.ShioajiLiveBootstrap",
            return_value=boot,
        ):
            start_live_session(engine, coordinator=coord)
        boot.start_live.assert_called_once()
        tick = mock.MagicMock()
        boot.on_tick_from_shioaji(tick)
        coord.on_shioaji_tick.assert_called_once_with(tick)


if __name__ == "__main__":
    unittest.main()
