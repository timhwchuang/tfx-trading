"""FT-023 wash-beta CF simulator tests."""

from __future__ import annotations

import datetime as dt
import unittest

from strategy_gudt_route_a.wash_beta import (
    WashBetaParams,
    build_wash_beta_replay_plan,
    simulate_wash_beta_day,
)


def _ctx(
    *,
    day: dt.date,
    open_px: float,
    ticks: list[tuple[int, float]],
    drive_low: float = 100.0,
) -> object:
    class _C:
        pass

    c = _C()
    c.day = day
    c.open_0845 = open_px
    c.atr = 50.0
    c.drive_high = open_px + 100
    c.drive_low = drive_low
    c.gap_pts = 30.0
    c.prior_close = open_px - 30
    c.ticks = [(ts, p, 1, 1) for ts, p in ticks]
    return c


class TestWashBetaSim(unittest.TestCase):
    def test_flatten_market_not_struct_stop(self) -> None:
        """Entry far below drive_low: exit must be flatten tick, not phantom stop."""
        day = dt.date(2026, 5, 6)
        start = int(dt.datetime.combine(day, dt.time(8, 45)).timestamp())
        flat = int(dt.datetime.combine(day, dt.time(13, 44)).timestamp())
        ctx = _ctx(
            day=day,
            open_px=41283.0,
            drive_low=41729.0,
            ticks=[(start, 41283.0), (start, 41288.0), (start + 1, 41290.0), (flat, 41350.0)],
        )
        sim = simulate_wash_beta_day(ctx, params=WashBetaParams())
        assert sim is not None
        self.assertEqual(sim["exit_reason"], "session_force_flatten")
        self.assertEqual(sim["exit_px"], 41350.0)
        self.assertNotAlmostEqual(sim["gross_pnl"], 446.0)
        self.assertGreater(sim["gross_pnl"], 0)

    def test_entry_uses_first_tick_at_session_open(self) -> None:
        day = dt.date(2026, 6, 3)
        start = int(dt.datetime.combine(day, dt.time(8, 45)).timestamp())
        flat = int(dt.datetime.combine(day, dt.time(13, 44)).timestamp())
        ctx = _ctx(
            day=day,
            open_px=100.0,
            ticks=[(start + 2, 101.0), (flat, 110.0)],
        )
        sim = simulate_wash_beta_day(ctx)
        assert sim is not None
        self.assertEqual(sim["entry_px"], 101.0)
        self.assertEqual(sim["exit_px"], 110.0)

    def test_no_ticks_returns_none(self) -> None:
        day = dt.date(2026, 6, 3)
        ctx = _ctx(day=day, open_px=100.0, ticks=[])
        self.assertIsNone(simulate_wash_beta_day(ctx))

    def test_replay_plan_exit_ts_min_hold(self) -> None:
        sim = {
            "entry_ts": 100,
            "entry_px": 100.0,
            "exit_ts": 100,
            "exit_px": 105.0,
            "exit_reason": "session_force_flatten",
            "net": 0.0,
            "gross_pnl": 5.0,
            "hold_sec": 0,
        }
        plan = build_wash_beta_replay_plan("2026-06-03", sim)
        self.assertEqual(plan.events[0].ts, 100)
        self.assertEqual(plan.events[1].ts, 101)

    def test_exit_before_entry_realigns_price(self) -> None:
        day = dt.date(2026, 6, 3)
        start = int(dt.datetime.combine(day, dt.time(8, 45)).timestamp())
        flat = int(dt.datetime.combine(day, dt.time(13, 44)).timestamp())
        del flat
        ctx = _ctx(
            day=day,
            open_px=100.0,
            ticks=[(start - 50, 95.0)],
        )
        sim = simulate_wash_beta_day(ctx)
        assert sim is not None
        self.assertGreaterEqual(sim["exit_ts"], sim["entry_ts"])
        self.assertEqual(sim["exit_px"], 100.0)
        self.assertEqual(sim["gross_pnl"], 0.0)

    def test_live_intraday_plan_schedules_config_flatten(self) -> None:
        day = dt.date(2026, 6, 3)
        start = int(dt.datetime.combine(day, dt.time(8, 45)).timestamp())
        flat = int(dt.datetime.combine(day, dt.time(13, 44)).timestamp())
        ctx = _ctx(day=day, open_px=100.0, ticks=[(start, 100.0)])
        from strategy_gudt_route_a.wash_beta import build_wash_beta_live_intraday_plan

        plan = build_wash_beta_live_intraday_plan(day.isoformat(), ctx)
        assert plan is not None
        self.assertEqual(plan.events[1].ts, flat)

    def test_replay_plan_pairs_entry_exit(self) -> None:
        day = "2026-06-03"
        sim = {
            "entry_ts": 1,
            "entry_px": 100.0,
            "exit_ts": 2,
            "exit_px": 105.0,
            "exit_reason": "session_force_flatten",
            "net": 0.0,
            "gross_pnl": 5.0,
            "hold_sec": 1,
        }
        plan = build_wash_beta_replay_plan(day, sim)
        self.assertEqual(plan.path, "wash_beta")
        self.assertFalse(plan.skipped)
        self.assertEqual(len(plan.events), 2)
        self.assertEqual(plan.events[0].leg, "long_entry")
        self.assertEqual(plan.events[1].leg, "long_exit")


if __name__ == "__main__":
    unittest.main()
