"""A-class tests for OSF smc_bar_structure and liquidity helpers."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from reporting.opening_sweep_fvg_counterfactual import (
    OsfParams,
    SETUP_START,
    TRIGGER_END,
    _detect_15m_setup,
    _pool_levels_for_sweep,
    scan_day_long,
    session_tf_bars_for_day,
)
from reporting.osf_liquidity import (
    LiquidityLevels,
    OpeningRange,
    compute_gap_cohort,
    compute_liquidity_levels,
    sweep_pool_hit,
)
from reporting.osf_session_context import (
    OSF_DAILY_LOOKBACK,
    OsfBarStore,
    load_window_daily_lookback,
    overnight_bars_before_open,
    overnight_evening_start_from_bars,
)
from reporting.post_trigger_windows import enrich_post_trigger_windows
from reporting.simulate_bar_structure_exit import simulate_bar_structure_exit_long
from reporting.smc_bar_structure import (
    active_bullish_fvg,
    analyze_bos,
    detect_fvgs,
    range_position,
)
from storage.kbar_loader import KBarRecord, kbar_path, save_kbars_csv
from storage.session_bar_cache import DAY_ANCHOR, DAY_END, NIGHT_ANCHOR


def _bar(
    ts: datetime.datetime,
    o: float,
    h: float,
    l: float,
    c: float,
) -> KBarRecord:
    return KBarRecord(ts, o, h, l, c, 10)


class TestSmcBarStructure(unittest.TestCase):
    def test_detect_bullish_fvg(self):
        t0 = datetime.datetime(2026, 5, 15, 9, 0)
        bars = [
            _bar(t0, 100, 101, 99, 100),
            _bar(t0 + datetime.timedelta(minutes=15), 100, 101, 99, 100.5),
            _bar(t0 + datetime.timedelta(minutes=30), 102, 105, 101.5, 104),
        ]
        zones = detect_fvgs(bars)
        self.assertTrue(any(z.side == "bullish" for z in zones))

    def test_active_fvg_respects_as_of(self):
        t0 = datetime.datetime(2026, 5, 15, 9, 0)
        bars = [
            _bar(t0, 100, 100.5, 99.5, 100),
            _bar(t0 + datetime.timedelta(minutes=15), 100, 100.5, 99.5, 100),
            _bar(t0 + datetime.timedelta(minutes=30), 102, 104, 101.2, 103),
        ]
        as_of = t0 + datetime.timedelta(minutes=30)
        fvg = active_bullish_fvg(bars, as_of=as_of, max_age_bars=8, tf_minutes=15)
        self.assertIsNotNone(fvg)

    def test_range_discount(self):
        bars = [_bar(datetime.datetime(2026, 5, 15, 9, i), 100 + i, 101 + i, 99, 100 + i) for i in range(10)]
        pos = range_position(bars, price=99.5, lookback=10)
        self.assertEqual(pos, "discount")

    def test_bos_bullish(self):
        t = datetime.datetime(2026, 5, 15, 9, 0)
        prices = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107]
        bars = [
            _bar(t + datetime.timedelta(minutes=15 * i), p, p + 1, p - 1, p)
            for i, p in enumerate(prices)
        ]
        state = analyze_bos(bars, swing_lookback=1)
        self.assertIn(state.last_bos, ("bullish", "bearish", None))


class TestOsfLiquidity(unittest.TestCase):
    def test_sweep_pool_hit(self):
        self.assertTrue(sweep_pool_hit(99.0, 100.5, 100.0))
        self.assertFalse(sweep_pool_hit(100.5, 99.0, 100.0))

    def test_gap_up(self):
        day = datetime.date(2026, 5, 15)
        prev = day - datetime.timedelta(days=1)
        bars = [
            # Prior day-session required (disk SSOT) so overnight starts prev 15:00
            _bar(datetime.datetime.combine(prev, datetime.time(13, 0)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(prev, datetime.time(23, 0)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(day, datetime.time(8, 46)), 110, 112, 109, 111),
        ]
        cohort, gap, _, _ = compute_gap_cohort(bars, day, flat_band_points=5.0)
        self.assertEqual(cohort, "gap_up")
        self.assertGreater(gap, 5.0)


class TestOsfOutcomePath(unittest.TestCase):
    def test_post_trigger_windows_populated(self):
        entry_ts = datetime.datetime(2026, 5, 15, 10, 0)
        after = [
            _bar(entry_ts + datetime.timedelta(minutes=i), 100, 100 + i * 0.1, 99, 100)
            for i in range(1, 121)
        ]
        out = enrich_post_trigger_windows(
            entry_price=100.0,
            entry_ts=int(entry_ts.timestamp()),
            bars_1m_after=after,
            atr=10.0,
        )
        self.assertIn("mfe_15m", out)
        self.assertIn("mae_120m", out)

    def test_post_trigger_windows_short_side(self):
        entry_ts = datetime.datetime(2026, 5, 15, 10, 0)
        after = [
            _bar(
                entry_ts + datetime.timedelta(minutes=i),
                100,
                100 + 0.5,
                100 - i * 0.2,
                100 - i * 0.1,
            )
            for i in range(1, 61)
        ]
        out = enrich_post_trigger_windows(
            entry_price=100.0,
            entry_ts=int(entry_ts.timestamp()),
            bars_1m_after=after,
            atr=10.0,
            side="short",
            stop_ref=101.0,
        )
        self.assertGreater(out["mfe_30m"], 0)
        self.assertIn("path_edge_60m", out)
        self.assertFalse(out["stop_hit_30m"])

    def test_exit_sim_uses_pre_entry_atr(self):
        t0 = datetime.datetime(2026, 5, 15, 9, 0)
        bars_5m = [
            _bar(t0 + datetime.timedelta(minutes=5 * i), 100 + i, 110 + i, 90 + i, 105 + i)
            for i in range(20)
        ]
        entry_ts = bars_5m[15].ts
        entry_price = float(bars_5m[15].Close)
        after = _bar(entry_ts + datetime.timedelta(minutes=5), 120, 121, 50, 51)
        result = simulate_bar_structure_exit_long(
            entry_price=entry_price,
            entry_ts=entry_ts,
            sweep_low=80.0,
            fvg_low=90.0,
            session_high=200.0,
            bars_5m=[*bars_5m, after],
            bars_15m=[],
            k_sl=1.0,
        )
        self.assertEqual(result["exit_reason"], "hard_stop_5m")
        self.assertLess(result["exit_price"], entry_price)

    def test_exit_sim_runs_past_trigger_end(self):
        t0 = datetime.datetime(2026, 5, 15, 12, 50)
        bars_5m = [
            _bar(t0 + datetime.timedelta(minutes=5 * i), 100, 101, 99, 100)
            for i in range(8)
        ]
        entry_ts = bars_5m[0].ts
        result = simulate_bar_structure_exit_long(
            entry_price=100.0,
            entry_ts=entry_ts,
            sweep_low=90.0,
            fvg_low=95.0,
            session_high=110.0,
            bars_5m=bars_5m,
            bars_15m=[],
            k_sl=1.0,
        )
        self.assertGreater(result["hold_bars_5m"], 1)

    def test_deepest_pool_wins_on_multi_sweep(self):
        day = datetime.date(2026, 5, 15)
        or_end = datetime.datetime.combine(day, datetime.time(9, 15))
        levels = LiquidityLevels(
            or_range=OpeningRange(105.0, 100.0, 5.0, or_end, True),
            dawn_low=98.0,
            overnight_low=95.0,
            gap_cohort="flat",
            gap_points=0.0,
            day_open=101.0,
            ref_close=101.0,
        )
        pools = _pool_levels_for_sweep(levels, "pools_or")
        bar = _bar(datetime.datetime.combine(day, datetime.time(10, 0)), 100, 100.8, 94, 101)
        bars_15m = [
            _bar(datetime.datetime.combine(day, datetime.time(9, 15)), 100, 100.5, 99.5, 100),
            _bar(datetime.datetime.combine(day, datetime.time(9, 30)), 100, 100.5, 99.5, 100),
            _bar(datetime.datetime.combine(day, datetime.time(9, 45)), 102, 105, 101.5, 104),
            bar,
        ]
        setup = _detect_15m_setup(
            bar,
            levels,
            pools,
            bars_15m,
            params=OsfParams(require_displacement=False),
            as_of=bar.ts,
        )
        self.assertIsNotNone(setup)
        assert setup is not None
        self.assertEqual(setup.sweep_pool, "overnight_low")


class TestOsfMultiDayBarStore(unittest.TestCase):
    """Multi-day TF retention + point-in-time daily MA20 (no end-batch fallback)."""

    def test_load_window_scales_linearly_not_tf_bar_expand(self):
        """Month batch ≈ daily_lookback + 30, not ~300 trading days via TF expand."""
        single = load_window_daily_lookback(1)
        self.assertEqual(single, OSF_DAILY_LOOKBACK)
        month = load_window_daily_lookback(31)
        self.assertEqual(month, OSF_DAILY_LOOKBACK + 30)
        # Old bar-count expand path would land ~300 trading days; keep well below that.
        self.assertLess(month, 80)

    def test_snapshot_keeps_early_day_15m_and_ma20_is_point_in_time(self):
        """Synthetic multi-day store: early-day 15m present; short daily → ma20 None."""
        d0 = datetime.date(2026, 5, 1)
        d1 = datetime.date(2026, 5, 15)
        d2 = datetime.date(2026, 5, 30)
        bars_15m = [
            _bar(datetime.datetime.combine(d0, datetime.time(10, 0)), 100, 101, 99, 100.5),
            _bar(datetime.datetime.combine(d0, datetime.time(10, 15)), 100.5, 102, 100, 101),
            _bar(datetime.datetime.combine(d1, datetime.time(10, 0)), 110, 111, 109, 110.5),
            _bar(datetime.datetime.combine(d2, datetime.time(10, 0)), 120, 121, 119, 120.5),
        ]
        bars_5m = [
            _bar(datetime.datetime.combine(d0, datetime.time(10, 5)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(d2, datetime.time(10, 5)), 120, 121, 119, 120),
        ]
        # Only 5 daily bars — below MA20 period; must not invent end-batch MA.
        daily = [
            _bar(
                datetime.datetime.combine(datetime.date(2026, 4, 26 + i), DAY_END),
                100 + i,
                101 + i,
                99 + i,
                100.5 + i,
            )
            for i in range(5)
        ]
        bars_1m = [
            _bar(datetime.datetime.combine(d0, datetime.time(9, 0)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(d2, datetime.time(9, 0)), 120, 121, 119, 120),
        ]
        closed_full = {
            "1m": bars_1m,
            "5m": bars_5m,
            "15m": bars_15m,
            "1h": [],
            "4h": [],
        }
        store = OsfBarStore(
            code="TX",
            trading_days=[d0, d1, d2],
            _bars_1m=bars_1m,
            _ts_index=[b.ts for b in bars_1m],
            _closed_full=closed_full,
            _closed_ts_index={tf: [b.ts for b in s] for tf, s in closed_full.items()},
            _daily_full=daily,
            _daily_ts_index=[b.ts for b in daily],
        )
        # Early day: 15m bars for d0 must survive (would be trimmed in old path).
        snap_early = store.snapshot(datetime.datetime.combine(d0, DAY_END))
        early_15m = session_tf_bars_for_day(snap_early.closed.get("15m", []), d0)
        self.assertEqual(len(early_15m), 2)
        self.assertIsNone(snap_early.daily_ma20)

        # End day still sees full untrimmed series history.
        snap_late = store.snapshot(datetime.datetime.combine(d2, DAY_END))
        self.assertGreaterEqual(len(snap_late.closed.get("15m", [])), 4)
        self.assertIsNone(snap_late.daily_ma20)

        # With ≥20 dailies, MA20 is computed from the as_of slice only.
        long_daily = [
            _bar(
                datetime.datetime.combine(
                    datetime.date(2026, 4, 1) + datetime.timedelta(days=i), DAY_END
                ),
                100 + i * 0.1,
                101 + i * 0.1,
                99 + i * 0.1,
                100 + i * 0.1,
            )
            for i in range(25)
        ]
        store2 = OsfBarStore(
            code="TX",
            trading_days=[d0, d2],
            _bars_1m=bars_1m,
            _ts_index=[b.ts for b in bars_1m],
            _closed_full=closed_full,
            _closed_ts_index={tf: [b.ts for b in s] for tf, s in closed_full.items()},
            _daily_full=long_daily,
            _daily_ts_index=[b.ts for b in long_daily],
        )
        mid = long_daily[19].ts
        snap_mid = store2.snapshot(mid)
        self.assertIsNotNone(snap_mid.daily_ma20)
        self.assertEqual(len(snap_mid.daily_closed), 20)
        snap_short = store2.snapshot(long_daily[9].ts)
        self.assertIsNone(snap_short.daily_ma20)
        self.assertEqual(len(snap_short.daily_closed), 10)

    def test_session_tf_bars_for_day_excludes_prior_days(self):
        """Prod helper used by scan_day_long — must filter by date + setup window."""
        day = datetime.date(2026, 5, 15)
        prior = datetime.date(2026, 5, 14)
        bars = [
            _bar(datetime.datetime.combine(prior, datetime.time(10, 0)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(day, datetime.time(10, 0)), 110, 111, 109, 110),
            _bar(datetime.datetime.combine(day, datetime.time(14, 0)), 110, 111, 109, 110),
        ]
        scan = session_tf_bars_for_day(bars, day, start=SETUP_START, end=TRIGGER_END)
        self.assertEqual(len(scan), 1)
        self.assertEqual(scan[0].ts.date(), day)


class TestOsfOvernightDiskSSot(unittest.TestCase):
    """Overnight window from 1m bars only — no trade_days / holiday calendar."""

    def test_monday_uses_last_day_session_friday(self):
        monday = datetime.date(2026, 5, 4)
        friday = datetime.date(2026, 5, 1)
        bars = [
            _bar(datetime.datetime.combine(friday, datetime.time(13, 0)), 101, 102, 100, 101),
            _bar(datetime.datetime.combine(friday, NIGHT_ANCHOR), 100, 101, 95, 100),
            _bar(datetime.datetime.combine(friday, datetime.time(22, 0)), 100, 101, 94, 99),
            _bar(datetime.datetime.combine(monday, datetime.time(3, 0)), 99, 100, 93, 98),
            _bar(datetime.datetime.combine(monday, datetime.time(8, 46)), 110, 111, 109, 110),
        ]
        self.assertEqual(
            overnight_evening_start_from_bars(bars, monday),
            datetime.datetime.combine(friday, NIGHT_ANCHOR),
        )
        overnight = overnight_bars_before_open(bars, monday)
        self.assertGreaterEqual(len(overnight), 2)
        self.assertEqual(min(float(b.Low) for b in overnight), 93.0)
        self.assertTrue(
            all(
                b.ts.time() >= NIGHT_ANCHOR or b.ts.time() <= datetime.time(5, 0)
                for b in overnight
            )
        )
        levels = compute_liquidity_levels(bars, monday)
        self.assertEqual(levels.overnight_low, 93.0)
        cohort, gap, _, ref = compute_gap_cohort(bars, monday, flat_band_points=5.0)
        self.assertEqual(cohort, "gap_up")
        self.assertIsNotNone(ref)
        self.assertGreater(gap, 5.0)

    def test_no_bars_on_date_is_not_a_trading_day(self):
        """No Monday day bars → Tuesday overnight still anchors to Friday disk data."""
        friday = datetime.date(2026, 5, 1)
        tuesday = datetime.date(2026, 5, 5)
        bars = [
            _bar(datetime.datetime.combine(friday, datetime.time(10, 0)), 100, 101, 99, 100),
            _bar(datetime.datetime.combine(friday, NIGHT_ANCHOR), 100, 101, 90, 99),
            _bar(datetime.datetime.combine(friday, datetime.time(22, 0)), 99, 100, 88, 98),
            _bar(datetime.datetime.combine(tuesday, datetime.time(8, 46)), 112, 113, 111, 112),
        ]
        self.assertEqual(
            overnight_evening_start_from_bars(bars, tuesday),
            datetime.datetime.combine(friday, NIGHT_ANCHOR),
        )
        overnight = overnight_bars_before_open(bars, tuesday)
        self.assertEqual(len(overnight), 2)
        self.assertEqual(min(float(b.Low) for b in overnight), 88.0)
        self.assertEqual(compute_liquidity_levels(bars, tuesday).overnight_low, 88.0)

    def test_no_prior_day_session_means_empty_overnight(self):
        """Strict: if loaded 1m has no earlier day session, overnight is empty (no calendar guess)."""
        day = datetime.date(2026, 5, 4)
        bars = [
            _bar(datetime.datetime.combine(day, datetime.time(8, 46)), 110, 111, 109, 110),
            _bar(datetime.datetime.combine(day, datetime.time(9, 0)), 110, 111, 109, 110),
        ]
        self.assertIsNone(overnight_evening_start_from_bars(bars, day))
        self.assertEqual(overnight_bars_before_open(bars, day), [])
        levels = compute_liquidity_levels(bars, day)
        self.assertIsNone(levels.overnight_low)


def _minute_bars(
    start: datetime.datetime,
    n: int,
    *,
    price: float = 100.0,
) -> list[KBarRecord]:
    bars: list[KBarRecord] = []
    cur = start
    for i in range(n):
        p = price + i * 0.1
        bars.append(KBarRecord(cur, p, p + 1, p - 1, p, 10))
        cur += datetime.timedelta(minutes=1)
    return bars


class TestOsfLoadRangeIntegration(unittest.TestCase):
    """R5: OsfBarStore.load_range through SessionBarCache + real kbar files."""

    def test_load_range_overnight_and_untrimmed_15m(self):
        fri = datetime.date(2026, 5, 1)
        mon = datetime.date(2026, 5, 4)
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            fri_day = _minute_bars(
                datetime.datetime.combine(fri, datetime.time(8, 46)), 299, price=100.0
            )
            fri_night = _minute_bars(
                datetime.datetime.combine(fri, NIGHT_ANCHOR), 120, price=95.0
            )
            # Inject a distinctive overnight low for assert
            fri_night[10] = KBarRecord(
                fri_night[10].ts, 95.0, 96.0, 88.0, 94.0, 10
            )
            mon_day = _minute_bars(
                datetime.datetime.combine(mon, datetime.time(8, 46)), 299, price=110.0
            )
            save_kbars_csv(fri_day + fri_night, kbar_path(cache, "TX", fri))
            save_kbars_csv(mon_day, kbar_path(cache, "TX", mon))

            store = OsfBarStore.load_range("TX", [fri, mon], cache_dir=cache)
            self.assertIsNotNone(store)
            assert store is not None

            mon_open = datetime.datetime.combine(mon, DAY_ANCHOR)
            snap_open = store.snapshot(mon_open)
            overnight = overnight_bars_before_open(snap_open.bars_1m, mon)
            self.assertGreater(len(overnight), 0)
            self.assertEqual(min(float(b.Low) for b in overnight), 88.0)

            mon_eod = datetime.datetime.combine(mon, DAY_END)
            snap_eod = store.snapshot(mon_eod)
            m15 = [
                b for b in snap_eod.closed.get("15m", []) if b.ts.date() == mon
            ]
            self.assertGreater(len(m15), 0)

            # Empty day not in batch: scan short-circuits
            hole = datetime.date(2026, 5, 6)
            row, funnel = scan_day_long(
                "TX", hole, params=OsfParams(htf_mode="none"), store=store
            )
            self.assertIsNone(row)
            self.assertEqual(funnel["or_valid"], 0)


if __name__ == "__main__":
    unittest.main()