"""Unit tests for June story tune pure scanners (no disk)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from reporting.june_story_tune import (
    AMinusParams,
    APlusParams,
    CPlusParams,
    _h1_ok,
    _h4_ok,
    _passes_soft,
    _stop_long,
    _stop_short,
    iter_a_minus_grid,
    iter_a_plus_grid,
    iter_c_plus_grid,
    scan_a_minus_short,
    scan_a_plus_long,
    scan_c_plus_long,
)


def _bar(ts: datetime.datetime, o: float, h: float, l: float, c: float) -> SimpleNamespace:
    return SimpleNamespace(ts=ts, Open=o, High=h, Low=l, Close=c)


def test_grid_sizes() -> None:
    assert len(iter_a_plus_grid()) == 12
    assert len(iter_c_plus_grid()) == 6
    assert len(iter_a_minus_grid()) == 6


def test_stack_and_stops() -> None:
    assert _h4_ok({"h4_ma20": "above", "h4_ma60": "above"}, "dual_above")
    assert not _h4_ok({"h4_ma20": "above", "h4_ma60": "below"}, "dual_above")
    assert _h4_ok({"h4_ma20": "below", "h4_ma60": "below"}, "dual_below")
    assert _h1_ok({"h1_ma20": "above"}, "not_below")
    assert not _h1_ok({"h1_ma20": "below"}, "not_below")
    # Missing h1_ma20: unknown ≠ below → pass under not_below
    assert _h1_ok({}, "not_below")
    assert _stop_long(100.0, 80.0, "or_mid") == 90.0
    assert _stop_short(100.0, 80.0, 105.0, "bar_high_plus_20") == 125.0
    assert all(p.key().startswith("A-+_") for p in iter_a_minus_grid())


def test_passes_soft_kill_rules() -> None:
    good = {
        "median_path_edge_60m": 12.0,
        "stop_hit_30m_rate": 0.2,
        "path_support_rate": 0.4,
    }
    assert _passes_soft(good, 5)
    assert not _passes_soft(good, 4)
    assert not _passes_soft({**good, "median_path_edge_60m": 7.0}, 5)
    assert not _passes_soft({**good, "stop_hit_30m_rate": 0.5}, 5)
    assert not _passes_soft({**good, "path_support_rate": 0.0}, 5)


def test_scan_a_plus_first_break_only() -> None:
    day = datetime.date(2026, 6, 1)
    # 09:45 close above OR; 5m hold; later 10:15 would also break — ignored
    bars_15m = [
        _bar(datetime.datetime(2026, 6, 1, 9, 45), 100, 111, 99, 110),
        _bar(datetime.datetime(2026, 6, 1, 10, 15), 110, 120, 109, 119),
    ]
    bars_5m = [
        _bar(datetime.datetime(2026, 6, 1, 9, 50), 110, 112, 109, 111),  # Low 109 >= or_high 100
    ]
    # hold requires Low >= or_high=100 and bullish — 109>=100, 111>110 ok
    params = APlusParams(h4="none", h1="none", stop="or_mid", hold_bars=3)
    sig = scan_a_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        or_high=100.0,
        or_low=80.0,
        pvm={},
        params=params,
        regime_tag="t",
    )
    assert sig is not None
    assert sig["entry_ts"] == "2026-06-01T09:50:00"
    assert sig["stop_ref"] == 90.0


def test_scan_a_plus_any_of_hold_window() -> None:
    """First 5m fails hold; second within hold_bars succeeds."""
    day = datetime.date(2026, 6, 1)
    bars_15m = [_bar(datetime.datetime(2026, 6, 1, 9, 45), 100, 111, 99, 110)]
    bars_5m = [
        _bar(datetime.datetime(2026, 6, 1, 9, 50), 110, 112, 95, 111),  # Low under OR
        _bar(datetime.datetime(2026, 6, 1, 9, 55), 111, 113, 110, 112),  # hold ok
    ]
    params = APlusParams(h4="none", h1="none", stop="or_mid", hold_bars=3)
    sig = scan_a_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        or_high=100.0,
        or_low=80.0,
        pvm={},
        params=params,
        regime_tag="t",
    )
    assert sig is not None
    assert sig["entry_ts"] == "2026-06-01T09:55:00"


def test_scan_c_plus_pool_or_only_filters() -> None:
    day = datetime.date(2026, 6, 2)
    # Sweep overnight only (not or_low=100)
    bars_15m = [_bar(datetime.datetime(2026, 6, 2, 10, 0), 100, 105, 90, 102)]
    bars_5m = [_bar(datetime.datetime(2026, 6, 2, 10, 5), 102, 106, 101, 106)]
    pools = [("or_low", 100.0), ("overnight_low", 95.0)]
    params = CPlusParams(h4="none", pool="or_only", stop_buffer=0.0)
    # low 90 < or_low 100 < close 102 → would hit or_low if allowed
    # with overnight-only deep: if or_only, or_low 100 is in pools; low 90 < 100 < 102
    sig = scan_c_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        pools=pools,
        pvm={},
        params=params,
        regime_tag="t",
    )
    assert sig is not None
    assert "or_low" in sig["rationale"]
    # pools_pref prefers overnight when present
    params2 = CPlusParams(h4="none", pool="pools_pref", stop_buffer=20.0)
    sig2 = scan_c_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        pools=pools,
        pvm={},
        params=params2,
        regime_tag="t",
    )
    assert sig2 is not None
    assert "overnight_low" in sig2["rationale"]
    assert sig2["stop_ref"] == 70.0  # low 90 - 20


def test_scan_a_plus_failed_hold_no_second_break() -> None:
    day = datetime.date(2026, 6, 1)
    bars_15m = [
        _bar(datetime.datetime(2026, 6, 1, 9, 45), 100, 111, 99, 110),
        _bar(datetime.datetime(2026, 6, 1, 10, 15), 110, 120, 109, 119),
    ]
    # First break: next 5m fails hold. Later good 5m is outside hold_bars=1 window
    # and after first-break-only return — second 15m must not fire.
    bars_5m = [
        _bar(datetime.datetime(2026, 6, 1, 9, 50), 110, 112, 95, 111),
        _bar(datetime.datetime(2026, 6, 1, 10, 20), 119, 121, 118, 120),
    ]
    params = APlusParams(h4="none", h1="none", stop="or_low", hold_bars=1)
    sig = scan_a_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        or_high=100.0,
        or_low=80.0,
        pvm={},
        params=params,
        regime_tag="t",
    )
    assert sig is None


def test_scan_a_plus_h4_filter() -> None:
    day = datetime.date(2026, 6, 1)
    bars_15m = [_bar(datetime.datetime(2026, 6, 1, 9, 45), 100, 111, 99, 110)]
    bars_5m = [_bar(datetime.datetime(2026, 6, 1, 9, 50), 110, 112, 109, 111)]
    params = APlusParams(h4="dual_above", h1="none", stop="or_mid", hold_bars=3)
    assert (
        scan_a_plus_long(
            day,
            bars_15m=bars_15m,  # type: ignore[arg-type]
            bars_5m=bars_5m,  # type: ignore[arg-type]
            or_high=100.0,
            or_low=80.0,
            pvm={"h4_ma20": "below", "h4_ma60": "below"},
            params=params,
            regime_tag="t",
        )
        is None
    )


def test_scan_c_plus_reclaim() -> None:
    day = datetime.date(2026, 6, 2)
    bars_15m = [
        _bar(datetime.datetime(2026, 6, 2, 10, 0), 100, 105, 90, 102),  # sweep 95 reclaim
    ]
    bars_5m = [
        _bar(datetime.datetime(2026, 6, 2, 10, 5), 102, 106, 101, 106),  # > sweep high 105
    ]
    params = CPlusParams(h4="none", pool="any", stop_buffer=0.0)
    sig = scan_c_plus_long(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        bars_5m=bars_5m,  # type: ignore[arg-type]
        pools=[("or_low", 95.0)],
        pvm={},
        params=params,
        regime_tag="t",
    )
    assert sig is not None
    assert sig["story_id"] == "C+"
    assert sig["stop_ref"] == 90.0
    assert sig["entry_ref"] == 106.0


def test_scan_a_minus_require_below() -> None:
    day = datetime.date(2026, 6, 5)
    bars_15m = [
        _bar(datetime.datetime(2026, 6, 5, 10, 0), 100, 101, 78, 79),  # break or_low=80
    ]
    params = AMinusParams(h4="none", h1="require_below", stop="or_mid")
    assert (
        scan_a_minus_short(
            day,
            bars_15m=bars_15m,  # type: ignore[arg-type]
            or_high=100.0,
            or_low=80.0,
            pvm={"h1_ma20": "above"},
            params=params,
            regime_tag="t",
        )
        is None
    )
    sig = scan_a_minus_short(
        day,
        bars_15m=bars_15m,  # type: ignore[arg-type]
        or_high=100.0,
        or_low=80.0,
        pvm={"h1_ma20": "below"},
        params=params,
        regime_tag="t",
    )
    assert sig is not None
    assert sig["side"] == "short"
    assert sig["stop_ref"] == 90.0  # or_mid
