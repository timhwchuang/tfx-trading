"""P0-6: exchange-time session boundary tests."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.calendar.taifex import (
    exchange_date,
    is_at_or_after,
    is_opening_session_window,
    is_trading_session,
    resolve_active_session,
    select_recent_trading_days_closes,
    trading_day_for_daily_reset,
)
from trading_engine.testing.defaults import default_test_settings
from trading_engine.testing.helpers import make_host


def _dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute, second)


class TestTradingSessionBoundaries(unittest.TestCase):
    def test_before_session_start(self):
        s = default_test_settings()
        self.assertFalse(is_trading_session(_dt(8, 44, 59), s.session_start, s.session_end))

    def test_session_start_inclusive(self):
        s = default_test_settings()
        self.assertTrue(is_trading_session(_dt(8, 45, 0), s.session_start, s.session_end))

    def test_before_session_end(self):
        s = default_test_settings()
        self.assertTrue(is_trading_session(_dt(13, 44, 59), s.session_start, s.session_end))

    def test_session_end_inclusive(self):
        s = default_test_settings()
        self.assertTrue(is_trading_session(_dt(13, 45, 0), s.session_start, s.session_end))

    def test_after_session_end(self):
        s = default_test_settings()
        self.assertFalse(is_trading_session(_dt(13, 45, 1), s.session_start, s.session_end))


class TestExchangeDate(unittest.TestCase):
    def test_naive_date(self):
        self.assertEqual(exchange_date(_dt(8, 45)), datetime.date(2026, 6, 10))

    def test_utc_converts_to_taiwan_date(self):
        utc = datetime.datetime(2026, 6, 9, 16, 30, tzinfo=datetime.UTC)
        self.assertEqual(exchange_date(utc), datetime.date(2026, 6, 10))


class TestOvernightSession(unittest.TestCase):
    def test_overnight_window(self):
        start, end = datetime.time(15, 0), datetime.time(5, 0)
        self.assertTrue(is_trading_session(_dt(15, 0), start, end))
        self.assertTrue(is_trading_session(_dt(23, 0), start, end))
        self.assertTrue(is_trading_session(_dt(4, 59), start, end))
        self.assertFalse(is_trading_session(_dt(5, 1), start, end))
        self.assertFalse(is_trading_session(_dt(12, 0), start, end))

    def test_night_flatten_not_triggered_in_evening(self):
        start, end = datetime.time(15, 0), datetime.time(5, 0)
        flatten = datetime.time(4, 50)
        self.assertFalse(
            is_at_or_after(_dt(15, 30), flatten, session_start=start, session_end=end)
        )
        self.assertFalse(
            is_at_or_after(_dt(4, 49), flatten, session_start=start, session_end=end)
        )
        self.assertTrue(
            is_at_or_after(_dt(4, 50), flatten, session_start=start, session_end=end)
        )

    def test_resolve_active_session_day_and_night(self):
        day = resolve_active_session(
            _dt(9, 0),
            day_start=datetime.time(8, 45),
            day_end=datetime.time(13, 45),
            day_flatten=datetime.time(13, 40),
            day_force=datetime.time(13, 44),
            night_enabled=True,
        )
        self.assertIsNotNone(day)
        assert day is not None
        self.assertEqual(day[0], datetime.time(8, 45))

        night = resolve_active_session(
            _dt(16, 0),
            day_start=datetime.time(8, 45),
            day_end=datetime.time(13, 45),
            day_flatten=datetime.time(13, 40),
            day_force=datetime.time(13, 44),
            night_enabled=True,
            night_start=datetime.time(15, 0),
            night_end=datetime.time(5, 0),
            night_flatten=datetime.time(4, 50),
            night_force=datetime.time(4, 55),
        )
        self.assertIsNotNone(night)
        assert night is not None
        self.assertEqual(night[0], datetime.time(15, 0))

    def test_trading_day_rolls_at_1500(self):
        self.assertEqual(
            trading_day_for_daily_reset(_dt(14, 59)), datetime.date(2026, 6, 10)
        )
        self.assertEqual(
            trading_day_for_daily_reset(_dt(15, 0)), datetime.date(2026, 6, 11)
        )
        self.assertEqual(
            trading_day_for_daily_reset(_dt(4, 0)), datetime.date(2026, 6, 10)
        )


class TestWeekdaySessionGate(unittest.TestCase):
    """Night/day windows must not open on weekend / closed-market gaps."""

    _DAY = (datetime.time(8, 45), datetime.time(13, 45))
    _NIGHT = (datetime.time(15, 0), datetime.time(5, 0))

    def test_weekend_and_closed_gaps_not_in_session(self):
        # Sat 16:00 — no Saturday night
        self.assertFalse(
            is_trading_session(datetime.datetime(2026, 6, 13, 16, 0), *self._NIGHT)
        )
        # Sun 02:00 — no overnight
        self.assertFalse(
            is_trading_session(datetime.datetime(2026, 6, 14, 2, 0), *self._NIGHT)
        )
        # Mon 03:00 — no Sunday→Monday night
        self.assertFalse(
            is_trading_session(datetime.datetime(2026, 6, 8, 3, 0), *self._NIGHT)
        )
        # Sat 10:00 — no weekend day session
        self.assertFalse(
            is_trading_session(datetime.datetime(2026, 6, 13, 10, 0), *self._DAY)
        )

    def test_weekday_night_and_dawn_open(self):
        # Fri evening night open
        self.assertTrue(
            is_trading_session(datetime.datetime(2026, 6, 12, 16, 0), *self._NIGHT)
        )
        # Sat dawn continues Fri night
        self.assertTrue(
            is_trading_session(datetime.datetime(2026, 6, 13, 3, 0), *self._NIGHT)
        )
        # Tue dawn continues Mon night
        self.assertTrue(
            is_trading_session(datetime.datetime(2026, 6, 9, 3, 0), *self._NIGHT)
        )
        # Wed day session (existing fixture weekday)
        self.assertTrue(is_trading_session(_dt(9, 0), *self._DAY))

    def test_resolve_active_session_weekend_none(self):
        self.assertIsNone(
            resolve_active_session(
                datetime.datetime(2026, 6, 13, 16, 0),
                day_start=datetime.time(8, 45),
                day_end=datetime.time(13, 45),
                day_flatten=datetime.time(13, 40),
                day_force=datetime.time(13, 44),
                night_enabled=True,
            )
        )


class TestOpeningSessionWindow(unittest.TestCase):
    def test_opening_window_boundaries(self):
        self.assertTrue(is_opening_session_window(_dt(8, 45, 0)))
        self.assertTrue(is_opening_session_window(_dt(9, 14, 59)))
        self.assertFalse(is_opening_session_window(_dt(9, 15, 0)))
        self.assertFalse(is_opening_session_window(_dt(8, 44, 59)))


class TestDailyStateReset(unittest.TestCase):
    def test_reset_on_exchange_date_change(self):
        host = make_host()
        host.daily_pnl = -150.0
        host.block_new_entry = True
        host.consecutive_loss = 3
        host._trading_date = datetime.date(2026, 6, 9)

        host._maybe_reset_daily_state(_dt(8, 45))

        self.assertEqual(host.daily_pnl, 0.0)
        self.assertFalse(host.block_new_entry)
        self.assertEqual(host.consecutive_loss, 0)
        self.assertEqual(host._trading_date, datetime.date(2026, 6, 10))

    def test_same_day_no_reset(self):
        host = make_host()
        host.daily_pnl = -80.0
        host.block_new_entry = True
        host._trading_date = datetime.date(2026, 6, 10)

        host._maybe_reset_daily_state(_dt(10, 0))

        self.assertEqual(host.daily_pnl, -80.0)
        self.assertTrue(host.block_new_entry)

    def test_night_and_following_day_share_trading_day_budget(self):
        """Mon 15:00 night + Tue day session share one TAIFEX trading day."""
        host = make_host()

        # Mon 16:00 → trading day Tue
        mon_night = datetime.datetime(2026, 6, 8, 16, 0)
        host._trading_date = None
        host._maybe_reset_daily_state(mon_night)
        self.assertEqual(host._trading_date, datetime.date(2026, 6, 9))
        host.daily_pnl = -50.0
        host.consecutive_loss = 2
        host.block_new_entry = True

        # Tue 09:00 → same trading day (Jun 9); must NOT reset
        tue_day = datetime.datetime(2026, 6, 9, 9, 0)
        host._maybe_reset_daily_state(tue_day)
        self.assertEqual(host._trading_date, datetime.date(2026, 6, 9))
        self.assertEqual(host.daily_pnl, -50.0)
        self.assertEqual(host.consecutive_loss, 2)
        self.assertTrue(host.block_new_entry)

        # Tue 15:00 → new trading day Wed; reset
        tue_night = datetime.datetime(2026, 6, 9, 15, 0)
        host._maybe_reset_daily_state(tue_night)
        self.assertEqual(host._trading_date, datetime.date(2026, 6, 10))
        self.assertEqual(host.daily_pnl, 0.0)
        self.assertEqual(host.consecutive_loss, 0)
        self.assertFalse(host.block_new_entry)


class TestGapForceFlatten(unittest.TestCase):
    def test_gap_with_position_forces_flatten(self):
        host = make_host()
        host.position_qty = 1
        host.position_dir = "Long"
        # 14:00 is between day end and night start
        gap = datetime.datetime(2026, 6, 10, 14, 0)
        risk = host._risk_gate(int(gap.timestamp()), gap)
        self.assertTrue(risk.force_flatten)
        self.assertTrue(risk.after_flatten_time)

    def test_gap_flat_no_force(self):
        host = make_host()
        host.position_qty = 0
        gap = datetime.datetime(2026, 6, 10, 14, 0)
        risk = host._risk_gate(int(gap.timestamp()), gap)
        self.assertFalse(risk.force_flatten)
        self.assertFalse(risk.after_flatten_time)


class TestP6Cal1RecentTradingDaySlice(unittest.TestCase):
    def _wall_ns(self, dt: datetime.datetime) -> int:
        return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1e9)

    def test_select_keeps_only_recent_days_and_includes_latest(self):
        d1 = datetime.datetime(2026, 6, 12, 9, 0)
        d2 = datetime.datetime(2026, 6, 13, 9, 0)
        day1 = [100.0 + i for i in range(5)]
        day2 = [110.0 + i for i in range(5)]
        all_c = day1 + day2
        all_ts = [self._wall_ns(d1 + datetime.timedelta(minutes=i)) for i in range(5)] + [
            self._wall_ns(d2 + datetime.timedelta(minutes=i)) for i in range(5)
        ]

        class R:
            ts = all_ts
            Close = all_c

        ref = d2 + datetime.timedelta(minutes=3)
        sliced = select_recent_trading_days_closes(R(), ref, max_days=2)
        self.assertEqual(len(sliced), 10)
        sliced1 = select_recent_trading_days_closes(R(), ref, max_days=1)
        self.assertEqual(sliced1, day2)
        self.assertEqual(trading_day_for_daily_reset(d2), trading_day_for_daily_reset(ref))

    def test_select_cross_night_gap_and_choppy_prior(self):
        d_prior = datetime.datetime(2026, 6, 12, 13, 40)
        d_new = datetime.datetime(2026, 6, 13, 8, 50)
        prior = [100.0] * 10
        new = [100.0 + i * 0.7 for i in range(15)]
        closes = prior + new
        tss = [self._wall_ns(d_prior + datetime.timedelta(minutes=i)) for i in range(10)] + [
            self._wall_ns(d_new + datetime.timedelta(minutes=i)) for i in range(15)
        ]

        class R2:
            ts = tss
            Close = closes

        sliced = select_recent_trading_days_closes(
            R2(), d_new + datetime.timedelta(minutes=5), max_days=1
        )
        self.assertEqual(sliced, new)


class TestCooldownUsesExchangeTs(unittest.TestCase):
    def test_exit_fill_records_exchange_ts_not_system_clock(self):
        host = make_host()
        exit_ts = 1_700_000_000
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.trailing_peak = 18020.0
        host.pending_intent = "exit"
        host.pending_exchange_ts = exit_ts

        host._apply_deal_fill(18011.0, is_buy=False)

        self.assertEqual(host.last_exit_time, exit_ts)
        self.assertNotEqual(host.last_exit_time, int(__import__("time").time()))


if __name__ == "__main__":
    unittest.main()
