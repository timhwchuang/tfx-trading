"""FT-007 Phase 0 v2: tick flow flip (sustained buy/sell ratio → opposite side surge)."""

from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.impulse_absorption_counterfactual import simulate_scalp_exit
from reporting.volatility_baseline import DEFAULT_ATR_PERIOD, atr_series_from_bars
from reporting.vwap_stretch_fade_counterfactual import session_bucket_for_ts
from storage.kbar_loader import load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates

SCHEMA_VERSION = 2
SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)

DEFAULT_SETUP_WINDOW_SEC = 60
DEFAULT_FLIP_WINDOW_SEC = 30
DEFAULT_SETUP_SIDE_RATIO = 0.62
DEFAULT_SETUP_SUSTAIN_SEC = 40
DEFAULT_FLIP_OPPOSITE_RATIO = 0.55
DEFAULT_FLIP_SAME_SIDE_MAX = 0.42
DEFAULT_STALL_ATR_K = 0.35
DEFAULT_MIN_SETUP_VOL = 40
DEFAULT_MIN_FLIP_VOL = 25
DEFAULT_SETUP_TIMEOUT_SEC = 120
DEFAULT_TP_POINTS = 12.0
DEFAULT_SL_POINTS = 10.0
DEFAULT_MAX_HOLD_SEC = 120
DEFAULT_COOLDOWN_SEC = 180
DEFAULT_MIN_ATR = 25.0

DEFAULT_FLIP_SURGE_MULT = 1.5
DEFAULT_FOOTPRINT_LEVEL_RATIO = 0.55
DEFAULT_FOOTPRINT_TOP_LEVELS = 3

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 20

FlowSide = Literal["buy", "sell"]
TradeDir = Literal["Long", "Short"]


@dataclass
class RollingFlowWindow:
    window_sec: int
    ticks: deque[tuple[int, int, int]] = field(default_factory=deque)
    buy_vol: int = 0
    sell_vol: int = 0

    def push(self, ts: int, volume: int, tick_type: int) -> None:
        self.ticks.append((ts, volume, tick_type))
        if tick_type == 1:
            self.buy_vol += volume
        elif tick_type == 2:
            self.sell_vol += volume
        cutoff = ts - self.window_sec
        while self.ticks and self.ticks[0][0] < cutoff:
            _ots, old_v, old_type = self.ticks.popleft()
            if old_type == 1:
                self.buy_vol -= old_v
            elif old_type == 2:
                self.sell_vol -= old_v

    @property
    def total_vol(self) -> int:
        return self.buy_vol + self.sell_vol

    @property
    def buy_ratio(self) -> float:
        total = self.total_vol
        return self.buy_vol / total if total > 0 else 0.5

    @property
    def sell_ratio(self) -> float:
        return 1.0 - self.buy_ratio

    def price_range(self, prices: dict[int, float]) -> float:
        if not self.ticks:
            return 0.0
        vals = [prices.get(t[0], 0.0) for t in self.ticks]
        vals = [v for v in vals if v > 0]
        if not vals:
            return 0.0
        return max(vals) - min(vals)


def _side_vol_between(
    ticks: list[tuple[int, float, int, int]],
    start_ts: int,
    end_ts: int,
    *,
    side: Literal["buy", "sell"],
) -> int:
    tick_type = 1 if side == "buy" else 2
    total = 0
    for ts, _price, vol, tt in ticks:
        if start_ts < ts <= end_ts and tt == tick_type:
            total += vol
    return total


def _ticks_in_window(
    ticks: list[tuple[int, float, int, int]],
    start_ts: int,
    end_ts: int,
) -> list[tuple[int, float, int, int]]:
    return [t for t in ticks if start_ts < t[0] <= end_ts]


def _footprint_confirms(
    setup_side: FlowSide,
    window_ticks: list[tuple[int, float, int, int]],
    *,
    top_levels: int = DEFAULT_FOOTPRINT_TOP_LEVELS,
    level_ratio_min: float = DEFAULT_FOOTPRINT_LEVEL_RATIO,
) -> bool:
    """Pseudo-footprint: opposite-side volume dominates at extreme price bins."""
    if not window_ticks:
        return False
    bins: dict[int, list[int]] = {}
    for _ts, price, vol, tick_type in window_ticks:
        level = int(round(price))
        slot = bins.setdefault(level, [0, 0])
        if tick_type == 1:
            slot[0] += vol
        elif tick_type == 2:
            slot[1] += vol
    if not bins:
        return False
    if setup_side == "buy":
        levels = sorted(bins.keys(), reverse=True)[:top_levels]
        for lv in levels:
            buy_v, sell_v = bins[lv]
            total = buy_v + sell_v
            if total > 0 and sell_v / total >= level_ratio_min:
                return True
        return False
    levels = sorted(bins.keys())[:top_levels]
    for lv in levels:
        buy_v, sell_v = bins[lv]
        total = buy_v + sell_v
        if total > 0 and buy_v / total >= level_ratio_min:
            return True
    return False


def _flip_surge_ok(
    setup_side: FlowSide,
    ticks: list[tuple[int, float, int, int]],
    ts: int,
    flip_window_sec: int,
    flip_surge_mult: float,
) -> bool:
    """Opposite-side volume in flip window vs prior window of equal length."""
    flip_start = ts - flip_window_sec
    prior_start = ts - 2 * flip_window_sec
    if setup_side == "buy":
        flip_vol = _side_vol_between(ticks, flip_start, ts, side="sell")
        prior_vol = _side_vol_between(ticks, prior_start, flip_start, side="sell")
    else:
        flip_vol = _side_vol_between(ticks, flip_start, ts, side="buy")
        prior_vol = _side_vol_between(ticks, prior_start, flip_start, side="buy")
    if prior_vol <= 0:
        return flip_vol > 0
    return flip_vol >= flip_surge_mult * prior_vol


def _session_ticks(code: str, day: dt.date, *, cache_dir: Path) -> list[tuple[int, float, int, int]]:
    rows: list[tuple[int, float, int, int]] = []
    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        t = tick.datetime.time()
        if t < SESSION_START or t > SESSION_END:
            continue
        rows.append(
            (
                int(tick.datetime.timestamp()),
                float(tick.close),
                int(tick.volume),
                int(tick.tick_type),
            )
        )
    return rows


def _day_atr(code: str, day: dt.date, *, cache_dir: Path) -> float:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return DEFAULT_MIN_ATR
    bars = load_kbars_csv(kpath)
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume))
        for b in bars
        if SESSION_START <= b.ts.time() <= SESSION_END
    ]
    atrs = atr_series_from_bars(tuples, period=DEFAULT_ATR_PERIOD)
    if not atrs:
        return DEFAULT_MIN_ATR
    return max(float(atrs[-1]), DEFAULT_MIN_ATR)


def _fade_direction(setup_side: FlowSide) -> TradeDir:
    return "Short" if setup_side == "buy" else "Long"


def detect_flow_flip_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    setup_window_sec: int = DEFAULT_SETUP_WINDOW_SEC,
    flip_window_sec: int = DEFAULT_FLIP_WINDOW_SEC,
    setup_side_ratio: float = DEFAULT_SETUP_SIDE_RATIO,
    setup_sustain_sec: int = DEFAULT_SETUP_SUSTAIN_SEC,
    flip_opposite_ratio: float = DEFAULT_FLIP_OPPOSITE_RATIO,
    flip_same_side_max: float = DEFAULT_FLIP_SAME_SIDE_MAX,
    stall_atr_k: float = DEFAULT_STALL_ATR_K,
    min_setup_vol: int = DEFAULT_MIN_SETUP_VOL,
    min_flip_vol: int = DEFAULT_MIN_FLIP_VOL,
    setup_timeout_sec: int = DEFAULT_SETUP_TIMEOUT_SEC,
    tp_points: float = DEFAULT_TP_POINTS,
    sl_points: float = DEFAULT_SL_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    close_1h_only: bool = False,
    footprint_enabled: bool = False,
    flip_surge_mult: float | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ticks = _session_ticks(code, day, cache_dir=cache_dir)
    if not ticks:
        return [], {"buy_setups": 0, "sell_setups": 0, "buy_flips": 0, "sell_flips": 0}

    atr = _day_atr(code, day, cache_dir=cache_dir)
    stall_pts = stall_atr_k * atr

    win_setup = RollingFlowWindow(setup_window_sec)
    win_flip = RollingFlowWindow(flip_window_sec)
    recent_prices: dict[int, float] = {}

    buy_sustain_start: int | None = None
    sell_sustain_start: int | None = None
    buy_ready_ts: int | None = None
    sell_ready_ts: int | None = None
    last_entry_ts: int | None = None

    rows: list[dict[str, Any]] = []
    stats = {"buy_setups": 0, "sell_setups": 0, "buy_flips": 0, "sell_flips": 0}

    def _try_entry(setup_side: FlowSide, bucket: str, ts: int, price: float) -> None:
        nonlocal last_entry_ts, buy_ready_ts, sell_ready_ts, buy_sustain_start, sell_sustain_start
        if close_1h_only and bucket != "close_1h":
            if setup_side == "buy":
                buy_ready_ts = None
                buy_sustain_start = None
            else:
                sell_ready_ts = None
                sell_sustain_start = None
            return
        flip_start = ts - flip_window_sec
        window_ticks = _ticks_in_window(ticks, flip_start, ts)
        if footprint_enabled and not _footprint_confirms(
            setup_side, window_ticks
        ):
            return
        if flip_surge_mult is not None and not _flip_surge_ok(
            setup_side, ticks, ts, flip_window_sec, flip_surge_mult
        ):
            return
        if setup_side == "buy":
            stats["buy_flips"] += 1
        else:
            stats["sell_flips"] += 1
        if last_entry_ts is not None and ts - last_entry_ts < cooldown_sec:
            if setup_side == "buy":
                buy_ready_ts = None
                buy_sustain_start = None
            else:
                sell_ready_ts = None
                sell_sustain_start = None
            return
        trade_dir = _fade_direction(setup_side)
        sim = simulate_scalp_exit(
            direction=trade_dir,
            entry_price=price,
            entry_ts=ts,
            ticks=ticks,
            tp_points=tp_points,
            sl_points=sl_points,
            max_hold_sec=max_hold_sec,
        )
        gross = float(sim["gross_pnl"])
        row: dict[str, Any] = {
            "day": day.isoformat(),
            "ts": ts,
            "setup_side": setup_side,
            "direction": trade_dir,
            "entry_price": round(price, 1),
            "atr": round(atr, 2),
            "flip_price_range": round(win_flip.price_range(recent_prices), 2),
            "stall_pts": round(stall_pts, 2),
            "session_bucket": bucket,
            "gross_scalp": gross,
            "net_scalp": gross - friction_points,
            "scalp_sim": sim,
        }
        if setup_side == "buy":
            row["buy_ratio_setup"] = round(win_setup.buy_ratio, 3)
            row["sell_ratio_flip"] = round(win_flip.sell_ratio, 3)
            row["buy_ratio_flip"] = round(win_flip.buy_ratio, 3)
        else:
            row["sell_ratio_setup"] = round(win_setup.sell_ratio, 3)
            row["buy_ratio_flip"] = round(win_flip.buy_ratio, 3)
            row["sell_ratio_flip"] = round(win_flip.sell_ratio, 3)
        rows.append(row)
        last_entry_ts = ts
        if setup_side == "buy":
            buy_ready_ts = None
            buy_sustain_start = None
        else:
            sell_ready_ts = None
            sell_sustain_start = None

    for ts, price, volume, tick_type in ticks:
        recent_prices[ts] = price
        # prune old price keys (keep flip window + margin)
        cutoff_price = ts - flip_window_sec - 5
        for old_ts in list(recent_prices.keys()):
            if old_ts < cutoff_price:
                del recent_prices[old_ts]

        win_setup.push(ts, volume, tick_type)
        win_flip.push(ts, volume, tick_type)

        bucket = session_bucket_for_ts(ts)
        if bucket == "out_of_session":
            continue

        # --- buy-dom setup (fade short) ---
        if (
            win_setup.buy_ratio >= setup_side_ratio
            and win_setup.total_vol >= min_setup_vol
        ):
            if buy_sustain_start is None:
                buy_sustain_start = ts
            elif buy_ready_ts is None and ts - buy_sustain_start >= setup_sustain_sec:
                buy_ready_ts = ts
                stats["buy_setups"] += 1
        else:
            buy_sustain_start = None
            if buy_ready_ts is not None and ts - buy_ready_ts > setup_timeout_sec:
                buy_ready_ts = None

        if buy_ready_ts is not None:
            if (
                win_flip.sell_ratio >= flip_opposite_ratio
                and win_flip.buy_ratio <= flip_same_side_max
                and win_flip.total_vol >= min_flip_vol
                and win_flip.price_range(recent_prices) <= stall_pts
            ):
                _try_entry("buy", bucket, ts, price)

        # --- sell-dom setup (fade long) ---
        if (
            win_setup.sell_ratio >= setup_side_ratio
            and win_setup.total_vol >= min_setup_vol
        ):
            if sell_sustain_start is None:
                sell_sustain_start = ts
            elif sell_ready_ts is None and ts - sell_sustain_start >= setup_sustain_sec:
                sell_ready_ts = ts
                stats["sell_setups"] += 1
        else:
            sell_sustain_start = None
            if sell_ready_ts is not None and ts - sell_ready_ts > setup_timeout_sec:
                sell_ready_ts = None

        if sell_ready_ts is not None:
            if (
                win_flip.buy_ratio >= flip_opposite_ratio
                and win_flip.sell_ratio <= flip_same_side_max
                and win_flip.total_vol >= min_flip_vol
                and win_flip.price_range(recent_prices) <= stall_pts
            ):
                _try_entry("sell", bucket, ts, price)

    return rows, stats


def _group_summary(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    return {
        g: {"scalp": _summarize_gross_net("gross_scalp", "net_scalp", sub)}
        for g, sub in sorted(groups.items())
    }


def _evaluate_phase0_gate(
    summary_by_setup_and_bucket: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for setup_side, buckets in summary_by_setup_and_bucket.items():
        for bucket, metrics in buckets.items():
            if bucket == "out_of_session":
                continue
            s = metrics.get("scalp") or {}
            n = int(s.get("n") or 0)
            gross = s.get("gross_mean")
            net = s.get("net_mean")
            if gross is None or net is None:
                continue
            candidate = {
                "setup_side": setup_side,
                "session_bucket": bucket,
                "n": n,
                "gross_mean": gross,
                "net_mean": net,
            }
            if n >= PHASE0_MIN_N and gross > PHASE0_GROSS_MIN and net > PHASE0_NET_MIN:
                passed = True
                if best is None or gross > best.get("gross_mean", 0):
                    best = candidate
    return {
        "pass": passed,
        "gross_mean_min": PHASE0_GROSS_MIN,
        "net_mean_min": PHASE0_NET_MIN,
        "min_n": PHASE0_MIN_N,
        "best_passing": best,
    }


def build_flow_flip_payload(
    *,
    code: str,
    cache_dir: Path,
    dates: list[dt.date] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    variant: str = "v2_baseline",
    setup_side_ratio: float = DEFAULT_SETUP_SIDE_RATIO,
    setup_sustain_sec: int = DEFAULT_SETUP_SUSTAIN_SEC,
    flip_opposite_ratio: float = DEFAULT_FLIP_OPPOSITE_RATIO,
    tp_points: float = DEFAULT_TP_POINTS,
    sl_points: float = DEFAULT_SL_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
    friction_points: float = FRICTION_POINTS,
    close_1h_only: bool = False,
    footprint_enabled: bool = False,
    flip_surge_mult: float | None = None,
) -> dict[str, Any]:
    if dates is None:
        if from_date is None or to_date is None:
            raise ValueError("provide dates or from_date/to_date")
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
        )
    if not dates:
        raise ValueError("no dates to process")

    all_rows: list[dict[str, Any]] = []
    diag_by_day: dict[str, dict[str, int]] = {}
    for day in dates:
        rows, stats = detect_flow_flip_entries_for_day(
            code,
            day,
            cache_dir=cache_dir,
            setup_side_ratio=setup_side_ratio,
            setup_sustain_sec=setup_sustain_sec,
            flip_opposite_ratio=flip_opposite_ratio,
            tp_points=tp_points,
            sl_points=sl_points,
            max_hold_sec=max_hold_sec,
            friction_points=friction_points,
            close_1h_only=close_1h_only,
            footprint_enabled=footprint_enabled,
            flip_surge_mult=flip_surge_mult,
        )
        all_rows.extend(rows)
        diag_by_day[day.isoformat()] = stats

    by_setup: dict[str, list[dict[str, Any]]] = {"buy": [], "sell": []}
    for row in all_rows:
        by_setup[str(row["setup_side"])].append(row)

    summary_by_setup = {
        side: {"scalp": _summarize_gross_net("gross_scalp", "net_scalp", rows)}
        for side, rows in by_setup.items()
    }
    summary_by_setup_and_bucket = {
        side: _group_summary(rows, "session_bucket") for side, rows in by_setup.items()
    }
    phase0_gate = _evaluate_phase0_gate(summary_by_setup_and_bucket)

    total_diag = {
        k: sum(d.get(k, 0) for d in diag_by_day.values())
        for k in ("buy_setups", "sell_setups", "buy_flips", "sell_flips")
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "flow_flip_exhaustion_v2",
        "variant": variant,
        "from_date": min(dates).isoformat(),
        "to_date": max(dates).isoformat(),
        "dates": [d.isoformat() for d in dates],
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "setup_window_sec": DEFAULT_SETUP_WINDOW_SEC,
            "flip_window_sec": DEFAULT_FLIP_WINDOW_SEC,
            "setup_side_ratio": setup_side_ratio,
            "setup_sustain_sec": setup_sustain_sec,
            "flip_opposite_ratio": flip_opposite_ratio,
            "flip_same_side_max": DEFAULT_FLIP_SAME_SIDE_MAX,
            "stall_atr_k": DEFAULT_STALL_ATR_K,
            "min_setup_vol": DEFAULT_MIN_SETUP_VOL,
            "min_flip_vol": DEFAULT_MIN_FLIP_VOL,
            "tp_points": tp_points,
            "sl_points": sl_points,
            "max_hold_sec": max_hold_sec,
            "close_1h_only": close_1h_only,
            "footprint_enabled": footprint_enabled,
            "flip_surge_mult": flip_surge_mult,
        },
        "flow_diagnostics": {"by_day": diag_by_day, "totals": total_diag},
        "phase0_gate": phase0_gate,
        "summary_by_setup_side": summary_by_setup,
        "summary_by_setup_and_bucket": summary_by_setup_and_bucket,
        "summary_by_direction": _group_summary(all_rows, "direction"),
        "entry_count": len(all_rows),
        "entries": all_rows,
    }
