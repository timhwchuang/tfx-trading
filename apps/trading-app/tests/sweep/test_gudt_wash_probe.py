"""Tests for FT-018b gudt_wash_probe (mock boundaries, no tick cache)."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    DayWashContext,
    DistributionHedgeParams,
    ProbeEntry,
    WashProbeTuning,
    apply_b_prime_composite_day,
    apply_hedge_distribution_short,
    classify_wash_label,
    distribution_confirm_pass,
    distribution_signal_at_p0,
    pre_break_br_at,
    rule_pick_for_day,
    rule_pick_b_prime_quick_stop_veto,
    simulate_distribution_short_leg,
    simulate_flow_bailout_exit,
    simulate_short_to_stop,
    _ft_veto_v10,
    _simulate_exit,
)
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit


def _ticks(prices: list[tuple[int, float]]) -> list[tuple[int, float, int, int]]:
    return [(ts, p, 1, 1) for ts, p in prices]


class TestSimExtensions(unittest.TestCase):
    def test_be_disabled_when_none(self) -> None:
        """be_trigger_atr_k=None must not arm breakeven."""
        sim = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=100.0,
            entry_ts=1_000,
            atr=30.0,
            ticks=_ticks([(1_001, 130), (1_002, 62)]),
            hard_stop_atr_k=1.25,
            be_trigger_atr_k=None,
            trail_arm_atr_k=2.0,
            trail_dist_atr_k=0.6,
            hard_tp_atr_k=3.0,
            min_atr_pts=25.0,
        )
        self.assertFalse(sim["be_armed"])
        self.assertEqual(sim["exit_reason"], "stop_loss")
        self.assertLess(sim["gross_pnl"], 0)

    def test_initial_stop_price_overrides_atr_stop(self) -> None:
        sim = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=100.0,
            entry_ts=1_000,
            atr=30.0,
            ticks=_ticks([(1_001, 94), (1_002, 80)]),
            hard_stop_atr_k=1.25,
            be_trigger_atr_k=None,
            trail_arm_atr_k=2.0,
            trail_dist_atr_k=0.6,
            hard_tp_atr_k=3.0,
            initial_stop_price=95.0,
            min_atr_pts=25.0,
        )
        self.assertEqual(sim["gross_pnl"], -5.0)
        self.assertEqual(sim["exit_reason"], "stop_loss")

    def test_max_hold_sec_1800(self) -> None:
        sim = simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=100.0,
            entry_ts=1_000,
            atr=30.0,
            ticks=_ticks([(1_100, 101), (2_800, 105), (2_801, 200)]),
            hard_stop_atr_k=1.25,
            be_trigger_atr_k=None,
            trail_arm_atr_k=2.0,
            trail_dist_atr_k=0.6,
            hard_tp_atr_k=None,
            max_hold_sec=1800,
            min_atr_pts=25.0,
        )
        self.assertEqual(sim["exit_reason"], "horizon")
        self.assertEqual(sim["gross_pnl"], 5.0)
        self.assertEqual(sim["hold_sec"], 1800)


class TestWashLabel(unittest.TestCase):
    def _ctx(self, atr: float = 40.0) -> DayWashContext:
        return DayWashContext(
            day=dt.date(2026, 2, 9),
            atr=atr,
            drive_high=100.0,
            drive_low=95.0,
            gap_pts=50.0,
            open_0845=1050.0,
            prior_close=1000.0,
            ticks=[],
            delta_br_at_reclaim=0.06,
        )

    def _entry(self) -> ProbeEntry:
        return ProbeEntry(
            entry_mode="p0",
            entry_ts=1_700_000_000,
            entry_price=101.0,
            br_at_entry=0.6,
            delta_br_at_entry=0.15,
            sell_ratio_at_entry=0.4,
            wash_depth=2.0,
            dip_below_dh=True,
        )

    def test_momentum_clean_high_mfe(self) -> None:
        label = classify_wash_label(
            entry=self._entry(),
            ctx=self._ctx(),
            w15=10.0,
            w30=20.0,
            w60=30.0,
            mfe=25.0,
            mae=5.0,
            dipped_below_dh=False,
        )
        self.assertEqual(label, "momentum_clean")

    def test_wash_fake(self) -> None:
        label = classify_wash_label(
            entry=self._entry(),
            ctx=self._ctx(),
            w15=5.0,
            w30=15.0,
            w60=20.0,
            mfe=10.0,
            mae=15.0,
            dipped_below_dh=True,
            friction=7.0,
        )
        self.assertEqual(label, "wash_fake")

    def test_wash_real(self) -> None:
        label = classify_wash_label(
            entry=self._entry(),
            ctx=self._ctx(),
            w15=-5.0,
            w30=-10.0,
            w60=-5.0,
            mfe=5.0,
            mae=20.0,
            dipped_below_dh=True,
        )
        self.assertEqual(label, "wash_real")


class TestExitModes(unittest.TestCase):
    def test_wash_struct_uses_initial_stop(self) -> None:
        ctx = DayWashContext(
            day=dt.date(2026, 2, 10),
            atr=40.0,
            drive_high=100.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=1050.0,
            prior_close=1000.0,
            ticks=_ticks([(100, 101), (101, 96), (102, 94)]),
            wash_low=94.0,
        )
        entry = ProbeEntry(
            entry_mode="flow_turn",
            entry_ts=100,
            entry_price=101.0,
            br_at_entry=0.6,
            delta_br_at_entry=0.15,
            sell_ratio_at_entry=0.4,
            wash_depth=6.0,
            dip_below_dh=True,
        )
        sim = _simulate_exit(entry, ctx, "wash_struct")
        self.assertFalse(sim["be_armed"])
        self.assertLess(sim["gross_pnl"], 0)

    def test_flow_bailout_e1_exits_weak_5min(self) -> None:
        entry_ts = 1_000
        atr = 40.0
        prices = [
            (entry_ts + 60, 100.0),
            (entry_ts + 180, 99.0),
            (entry_ts + 300, 94.0),
            (entry_ts + 400, 90.0),
        ]
        flow_ticks = [(ts, p, 50, 2 if p < 100 else 1) for ts, p in prices]
        sim = simulate_flow_bailout_exit(
            entry_price=100.0,
            entry_ts=entry_ts,
            atr=atr,
            ticks=flow_ticks,
            initial_stop_price=80.0,
        )
        self.assertEqual(sim["exit_reason"], "flow_bailout_e1")
        self.assertLess(sim["gross_pnl"], 0)

    def test_flow_bailout_drive_low_stop(self) -> None:
        entry_ts = 1_000
        sim = simulate_flow_bailout_exit(
            entry_price=100.0,
            entry_ts=entry_ts,
            atr=40.0,
            ticks=[(entry_ts + 30, 96.0, 10, 1), (entry_ts + 60, 93.0, 10, 1)],
            initial_stop_price=95.0,
        )
        self.assertEqual(sim["exit_reason"], "stop_loss")
        self.assertEqual(sim["gross_pnl"], -5.0)


class TestRulePick(unittest.TestCase):
    def _row(self, day: str, em: str, ex: str, ts: int, net: float, **extra: object) -> dict:
        base = {
            "day": day,
            "entry_mode": em,
            "exit_mode": ex,
            "entry_ts": ts,
            "entry_px": 100.0,
            "atr": 40.0,
            "drive_high": 110.0,
            "drive_low": 90.0,
            "net": net,
            "exit_reason": "horizon",
        }
        base.update(extra)
        return base

    def test_rule_b_early_ft(self) -> None:
        rows = [
            self._row("2026-02-09", "flow_turn", "flow_bailout", 100, 50.0),
            self._row("2026-02-09", "flow_turn", "drive_low_struct", 100, 45.0),
            self._row("2026-02-09", "p0", "sealed", 200, 10.0),
        ]
        pick = rule_pick_for_day(rows, rule="B", ft_exit="flow_bailout")
        assert pick is not None
        self.assertEqual(pick["path"], "flow_turn+flow_bailout")
        self.assertEqual(pick["net"], 50.0)

    def test_rule_b_prime_veto_falls_back_to_p0(self) -> None:
        from reporting.gap_drive_continuation_counterfactual import BREAK_START

        day = dt.date(2026, 2, 9)
        bs = int(dt.datetime.combine(day, BREAK_START).timestamp())
        ft_ts = bs + 20 * 60
        p0_ts = ft_ts + 600
        rows = [
            self._row("2026-02-09", "flow_turn", "flow_bailout", ft_ts, -30.0),
            self._row(
                "2026-02-09",
                "flow_turn",
                "drive_low_struct",
                ft_ts,
                -30.0,
                entry_px=60.0,
            ),
            self._row("2026-02-09", "p0", "sealed", p0_ts, 12.0),
        ]
        self.assertTrue(_ft_veto_v10(rows[1], has_p0=True))
        pick = rule_pick_for_day(rows, rule="B_prime", ft_exit="flow_bailout")
        assert pick is not None
        self.assertIn("veto", pick["path"])
        self.assertEqual(pick["net"], 12.0)

    def test_ft_only_toxic_zone_skipped(self) -> None:
        from reporting.gap_drive_continuation_counterfactual import BREAK_START

        day = dt.date(2026, 2, 9)
        bs = int(dt.datetime.combine(day, BREAK_START).timestamp())
        ft_ts = bs + 10 * 60
        rows = [
            self._row("2026-02-09", "flow_turn", "flow_bailout", ft_ts, -20.0),
            self._row(
                "2026-02-09",
                "flow_turn",
                "drive_low_struct",
                ft_ts,
                -20.0,
                entry_px=69.0,
            ),
        ]
        self.assertTrue(_ft_veto_v10(rows[1], has_p0=False))
        self.assertIsNone(rule_pick_for_day(rows, rule="B_prime", ft_exit="flow_bailout"))


class TestDistributionHedge(unittest.TestCase):
    def _ticks_dist(self) -> list[tuple[int, float, int, int]]:
        """Price falls after P0; sell-heavy flow at +10m (tick_type 2 = sell)."""
        base = 1000
        out: list[tuple[int, float, int, int]] = []
        for i in range(40):
            ts = base + i * 30
            px = 100.0 - i * 0.5
            tt = 2 if i >= 20 else 1
            out.append((ts, px, 10, tt))
        return out

    def test_distribution_signal_fires(self) -> None:
        ctx = DayWashContext(
            day=dt.date(2026, 6, 29),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=100.0,
            prior_close=50.0,
            ticks=self._ticks_dist(),
        )
        p0 = {"entry_ts": 1000, "entry_px": 100.0, "drive_high": 105.0}
        sig = distribution_signal_at_p0(p0, ctx)
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertLess(sig.flip_px, 100.0)
        self.assertLess(sig.br_at_flip, 0.42)

    def test_distribution_signal_no_fire_when_px_holds(self) -> None:
        ticks = [(1000 + i * 30, 101.0, 10, 2) for i in range(30)]
        ctx = DayWashContext(
            day=dt.date(2026, 6, 1),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=100.0,
            prior_close=50.0,
            ticks=ticks,
        )
        p0 = {"entry_ts": 1000, "entry_px": 100.0, "drive_high": 105.0}
        self.assertIsNone(distribution_signal_at_p0(p0, ctx))

    def test_short_stop_hit(self) -> None:
        ticks = [(1000, 100.0, 1, 1), (1010, 108.0, 1, 1)]
        sim = simulate_short_to_stop(
            ticks,
            entry_ts=1000,
            entry_px=100.0,
            stop_px=107.0,
            max_hold_sec=3600,
        )
        self.assertEqual(sim["exit_reason"], "stop_loss")
        self.assertEqual(sim["gross_pnl"], -7.0)

    def test_hedge_flip_replaces_long_net(self) -> None:
        ticks = self._ticks_dist()
        ctx = DayWashContext(
            day=dt.date(2026, 6, 29),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=100.0,
            prior_close=50.0,
            ticks=ticks,
        )
        day = "2026-06-29"
        rows = [
            {
                "day": day,
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -50.0,
                "exit_reason": "stop_loss",
            },
        ]
        pick = {"day": day, "path": "p0+sealed", "net": -50.0, "exit_reason": "stop_loss"}
        out = apply_hedge_distribution_short(pick, rows, ctx, friction=0.0)
        self.assertEqual(out["hedge"], "flip")
        self.assertNotEqual(out["net"], -50.0)
        self.assertGreater(out["short_net"], 0.0)

    def test_distribution_confirm_veto_on_bounce(self) -> None:
        # P0+10m signal with deep dump, then +2m bounce → confirm veto
        ticks = [
            (1000, 100.0, 10, 1),
            (1600, 74.0, 10, 2),
            (1720, 78.0, 10, 1),
        ]
        ctx = DayWashContext(
            day=dt.date(2026, 4, 10),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=100.0,
            prior_close=50.0,
            ticks=ticks,
        )
        p0 = {
            "entry_ts": 1000,
            "entry_px": 100.0,
            "drive_high": 105.0,
            "atr": 40.0,
        }
        sig = distribution_signal_at_p0(p0, ctx)
        self.assertIsNotNone(sig)
        assert sig is not None
        params = DistributionHedgeParams(
            confirm_sec=120,
            confirm_min_dump_atr=0.65,
            confirm_slope2_min=-0.35,
            confirm_slope2_max=0.0,
        )
        ok, metrics = distribution_confirm_pass(sig, p0, ctx, params=params)
        self.assertFalse(ok)
        assert metrics is not None
        self.assertGreater(metrics["slope2_atr"], 0.0)
        pick = {"day": "2026-04-10", "path": "p0+sealed", "net": -50.0}
        rows = [{**p0, "day": "2026-04-10", "entry_mode": "p0", "exit_mode": "sealed"}]
        out = apply_hedge_distribution_short(pick, rows, ctx, params=params, friction=0.0)
        self.assertEqual(out["hedge"], "none")
        self.assertEqual(out["dist_confirm"], "veto")


class TestBPrimeComposite(unittest.TestCase):
    def test_v4_skips_low_br5_day(self) -> None:
        # BR sampled at break_ts − 5min (30s window ending there)
        ticks = [(500 + i * 10, 100.0, 10, 2) for i in range(31)]
        ctx = DayWashContext(
            day=dt.date(2026, 6, 9),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=95.0,
            prior_close=50.0,
            ticks=ticks,
            first_break_ts=1100,
        )
        rows = [
            {
                "day": "2026-06-09",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -50.0,
                "exit_reason": "stop_loss",
            },
        ]
        br5 = pre_break_br_at(ctx)
        self.assertIsNotNone(br5)
        assert br5 is not None
        self.assertLess(br5, 0.35)
        out = apply_b_prime_composite_day(
            rows, ctx, params=BPrimeCompositeParams(pre_break_br_min=0.35)
        )
        self.assertIsNone(out)

    def test_v5_br5_p0_only_keeps_ft_day(self) -> None:
        ticks = [(500 + i * 10, 100.0, 10, 2) for i in range(31)]
        ctx = DayWashContext(
            day=dt.date(2026, 6, 9),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=95.0,
            prior_close=50.0,
            ticks=ticks,
            first_break_ts=1100,
        )
        rows = [
            {
                "day": "2026-06-09",
                "entry_mode": "flow_turn",
                "exit_mode": "drive_low_struct",
                "entry_ts": 800,
                "entry_px": 98.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": 47.0,
                "exit_reason": "trail",
            },
            {
                "day": "2026-06-09",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -50.0,
                "exit_reason": "stop_loss",
            },
        ]
        out = apply_b_prime_composite_day(
            rows,
            ctx,
            params=BPrimeCompositeParams(pre_break_br_min=0.35, pre_break_br_p0_only=True),
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("flow_turn", out["path"])

    def test_v5_flip_gated_by_ext_open(self) -> None:
        ticks = [(1000 + i * 30, 100.0 - i * 0.5, 10, 2 if i >= 20 else 1) for i in range(40)]
        ctx = DayWashContext(
            day=dt.date(2026, 6, 29),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=95.0,  # ext_open = (105-95)/40 = 0.25 < 5
            prior_close=50.0,
            ticks=ticks,
            first_break_ts=1000,
        )
        rows = [
            {
                "day": "2026-06-29",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -50.0,
                "exit_reason": "stop_loss",
            },
        ]
        out = apply_b_prime_composite_day(
            rows,
            ctx,
            params=BPrimeCompositeParams(
                pre_break_br_min=None,
                flip_min_ext_open=5.0,
            ),
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["hedge"], "none")

    def test_short_only_on_signal(self) -> None:
        ticks = [(1000 + i * 30, 100.0 - i * 0.5, 10, 2 if i >= 20 else 1) for i in range(40)]
        ctx = DayWashContext(
            day=dt.date(2026, 6, 29),
            atr=40.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=50.0,
            open_0845=95.0,
            prior_close=50.0,
            ticks=ticks,
            first_break_ts=1000,
        )
        rows = [
            {
                "day": "2026-06-29",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 40.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -50.0,
                "exit_reason": "stop_loss",
            },
        ]
        out = apply_b_prime_composite_day(
            rows,
            ctx,
            params=BPrimeCompositeParams(pre_break_br_min=None, short_only=True),
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["hedge"], "short_only")
        self.assertGreater(out["net"], 0.0)

    def test_ext_open_veto_routes_early_ft_to_p0(self) -> None:
        rows = [
            {
                "day": "2025-04-23",
                "entry_mode": "flow_turn",
                "exit_mode": "drive_low_struct",
                "entry_ts": 800,
                "entry_px": 98.0,
                "atr": 30.0,
                "drive_high": 200.0,
                "drive_low": 90.0,
                "open_0845": 49.0,
                "net": -46.0,
            },
            {
                "day": "2025-04-23",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 30.0,
                "drive_high": 200.0,
                "drive_low": 90.0,
                "open_0845": 49.0,
                "net": 58.0,
            },
        ]
        base = rule_pick_for_day(rows, rule="B_prime", ft_exit="drive_low_struct")
        assert base is not None
        self.assertIn("flow_turn", base["path"])
        veto = rule_pick_for_day(
            rows,
            rule="B_prime",
            ft_exit="drive_low_struct",
            ft_ext_open_min=5.0,
        )
        assert veto is not None
        self.assertIn("ext_open_veto", veto["path"])
        self.assertEqual(veto["net"], 58.0)

    def test_quick_stop_veto_routes_to_p0(self) -> None:
        import datetime as dt

        # stop within 4 min before break at ts=5000
        ticks = [(1000 + i * 20, 100.0 - i * 2, 10, 1) for i in range(20)]
        ctx = DayWashContext(
            day=dt.date(2025, 4, 23),
            atr=30.0,
            drive_high=105.0,
            drive_low=90.0,
            gap_pts=100.0,
            open_0845=80.0,
            prior_close=0.0,
            ticks=ticks,
            first_break_ts=5000,
        )
        rows = [
            {
                "day": "2025-04-23",
                "entry_mode": "flow_turn",
                "exit_mode": "drive_low_struct",
                "entry_ts": 1000,
                "entry_px": 100.0,
                "atr": 30.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": -46.0,
                "exit_reason": "stop_loss",
            },
            {
                "day": "2025-04-23",
                "entry_mode": "p0",
                "exit_mode": "sealed",
                "entry_ts": 4000,
                "entry_px": 102.0,
                "atr": 30.0,
                "drive_high": 105.0,
                "drive_low": 90.0,
                "net": 58.0,
                "exit_reason": "horizon",
            },
        ]
        pick = rule_pick_b_prime_quick_stop_veto(
            rows, ctx, ft_exit="drive_low_struct", quick_stop_max_sec=600
        )
        assert pick is not None
        self.assertIn("quick_stop_veto", pick["path"])
        self.assertEqual(pick["net"], 58.0)


if __name__ == "__main__":
    unittest.main()
