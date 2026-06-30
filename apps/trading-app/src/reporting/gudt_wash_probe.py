"""FT-018b: GUDT wash probe — entry×exit matrix, wash labels, single-day streaming."""

from __future__ import annotations

import csv
import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS
from reporting.flow_flip_counterfactual import RollingFlowWindow
from reporting.gap_drive_continuation_counterfactual import (
    BREAK_START,
    GdcParams,
    MIN_GAP_PTS,
    NO_NEW_ENTRY_AFTER,
    _atr_at_index,
    _drive_window_bars,
    _index_at_close_time,
    _load_gdc_day_context,
    _open_0845,
    _retrace_ok,
    _session_bars,
)
from reporting.post_entry_diagnosis import entry_window_stats
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit
from reporting.vwap_trend_pullback_counterfactual import _session_vwap_series
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates

EntryMode = Literal["p0", "flow_turn", "reclaim_br", "p0_quality"]
ExitMode = Literal[
    "sealed",
    "wash_struct",
    "drive_low_struct",
    "flow_bailout",
    "momentum_tail",
    "momentum_tail_trail",
]
WashLabel = Literal["momentum_clean", "wash_fake", "wash_real", "ambiguous"]

ENTRY_MODES: tuple[EntryMode, ...] = ("p0", "flow_turn", "reclaim_br", "p0_quality")
EXIT_MODES: tuple[ExitMode, ...] = (
    "sealed",
    "wash_struct",
    "drive_low_struct",
    "flow_bailout",
    "momentum_tail",
    "momentum_tail_trail",
)

DEFAULT_MIN_WASH_K = 0.25
DEFAULT_BR_MIN = 0.55
DEFAULT_DELTA_BR_MIN = 0.12
DEFAULT_BREAK_EPS = 0.05
FLOW_WINDOW_SEC = 30
WASH_STRUCT_DEPTH_K = 0.5
WASH_STOP_BUFFER = 2.0

SEALED_K_SL = 1.25
SEALED_BE = 0.75
SEALED_TRAIL_ARM = 2.0
SEALED_TRAIL_DIST = 0.6
SEALED_HARD_TP = 3.0
SEALED_MAX_HOLD = 900

FLOW_BAILOUT_E1_SEC = 300
FLOW_BAILOUT_E2_SEC = 600
FLOW_BAILOUT_BR3_SEC = 180
FLOW_BAILOUT_E1_ATR_K = 0.1
FLOW_BAILOUT_E1_BR_MAX = 0.52
FLOW_BAILOUT_E2_SLOPE_MIN = -0.08
FLOW_BAILOUT_HANDOFF_MFE_ATR_K = 1.5

# Counter-design v2: distribution flip (exit long + short) anchored on P0 + delay.
DIST_HEDGE_SIGNAL_SEC = 600
DIST_HEDGE_BR_MAX = 0.42
DIST_HEDGE_SHORT_STOP_PTS = 2.0
DIST_HEDGE_SHORT_MAX_HOLD_SEC = 3600

PANEL_DAYS_DEFAULT = (
    "2026-01-05",
    "2026-02-09",
    "2026-02-10",
    "2026-05-29",
    "2026-04-21",
    "2026-03-10",
)


@dataclass(frozen=True)
class WashProbeTuning:
    min_wash_k: float = DEFAULT_MIN_WASH_K
    br_min: float = DEFAULT_BR_MIN
    delta_br_min: float = DEFAULT_DELTA_BR_MIN
    break_eps: float = DEFAULT_BREAK_EPS
    gap_k_atr: float = 1.0
    retrace_max_frac: float = 0.4


@dataclass(frozen=True)
class DistributionHedgeParams:
    """Counter-design v2: flip long → short on post-P0 distribution."""

    signal_delay_sec: int = DIST_HEDGE_SIGNAL_SEC
    br_max: float = DIST_HEDGE_BR_MAX
    short_stop_pts: float = DIST_HEDGE_SHORT_STOP_PTS
    short_max_hold_sec: int = DIST_HEDGE_SHORT_MAX_HOLD_SEC
    # Phase-2 confirm (0 = immediate flip at signal_px; FT-018b Route A stack)
    confirm_sec: int = 0
    confirm_min_dump_atr: float | None = None
    confirm_slope2_min: float | None = None
    confirm_slope2_max: float | None = None


@dataclass(frozen=True)
class BPrimeCompositeParams:
    """B′ long + optional entry vetoes + distribution-short second leg."""

    pre_break_br_min: float | None = 0.35
    pre_break_br_p0_only: bool = False
    p0_ext_open_max: float | None = None
    p0_sess_vwap_dist_max: float | None = None
    flip_min_ext_open: float | None = None
    distribution: DistributionHedgeParams = DistributionHedgeParams()
    ft_exit: ExitMode = "drive_low_struct"
    short_only: bool = False


@dataclass(frozen=True)
class DistributionSignal:
    flip_ts: int
    flip_px: float
    br_at_flip: float
    p0_entry_px: float


@dataclass
class DayWashContext:
    day: dt.date
    atr: float
    drive_high: float
    drive_low: float
    gap_pts: float
    open_0845: float
    prior_close: float
    ticks: list[tuple[int, float, int, int]]
    session_bars: list[Any] | None = None
    first_break_ts: int | None = None
    wash_low: float | None = None
    wash_low_ts: int | None = None
    flow_turn_ts: int | None = None
    reclaim_ts: int | None = None
    delta_br_at_reclaim: float | None = None


@dataclass
class ProbeEntry:
    entry_mode: EntryMode
    entry_ts: int
    entry_price: float
    br_at_entry: float
    delta_br_at_entry: float
    sell_ratio_at_entry: float
    wash_depth: float
    dip_below_dh: bool
    vol_shrink_on_wash: bool = False


def _break_window_ts(day: dt.date) -> tuple[int, int]:
    break_start = int(dt.datetime.combine(day, BREAK_START).timestamp())
    deadline = int(dt.datetime.combine(day, NO_NEW_ENTRY_AFTER).timestamp())
    return break_start, deadline


def _vol_shrink_on_decline(
    ticks: list[tuple[int, float, int, int]],
    ts: int,
    *,
    lookback_sec: int = 90,
    bucket_sec: int = 30,
) -> tuple[float, bool]:
    """Sell ratio at ``ts``; shrink=True when price drifts down but sell vol falls."""
    start = ts - lookback_sec
    n_buckets = max(1, lookback_sec // bucket_sec)
    buckets: list[dict[str, float]] = [
        {"sell": 0.0, "total": 0.0, "last_px": 0.0} for _ in range(n_buckets)
    ]
    flow = RollingFlowWindow(FLOW_WINDOW_SEC)
    for tick_ts, price, vol, tick_type in ticks:
        if tick_ts > ts:
            break
        flow.push(tick_ts, vol, tick_type)
        if tick_ts < start:
            continue
        idx = min(n_buckets - 1, (tick_ts - start) // bucket_sec)
        buckets[idx]["total"] += vol
        if tick_type == 2:
            buckets[idx]["sell"] += vol
        buckets[idx]["last_px"] = price

    sell_at_ts = flow.sell_ratio
    active = [b for b in buckets if b["total"] > 0]
    if len(active) < 2:
        return sell_at_ts, False
    prices = [b["last_px"] for b in active if b["last_px"] > 0]
    sells = [b["sell"] for b in active]
    if len(prices) < 2:
        return sell_at_ts, False
    price_down = prices[-1] < prices[0]
    sell_shrink = sells[-1] < sells[0] * 0.85
    return sell_at_ts, bool(price_down and sell_shrink)


def _ticks_for_day(code: str, day: dt.date, cache_dir: Path) -> list[tuple[int, float, int, int]]:
    out: list[tuple[int, float, int, int]] = []
    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        ts = int(tick.datetime.timestamp())
        out.append((ts, float(tick.close), int(tick.volume), int(tick.tick_type)))
    return out


def _load_day_context(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    sorted_dates: list[dt.date],
    tuning: WashProbeTuning,
    gdc_bundle: tuple[list[Any], list[tuple[int, float, int, int]], float] | None = None,
) -> DayWashContext | None:
    bundle = gdc_bundle or _load_gdc_day_context(
        code, day, cache_dir=cache_dir, sorted_dates=sorted_dates
    )
    if bundle is None:
        return None
    bars, ticks, prior_close = bundle
    if prior_close is None:
        return None
    open_0845 = _open_0845(bars)
    if open_0845 is None:
        return None
    gap_pts = open_0845 - prior_close
    if gap_pts < MIN_GAP_PTS:
        return None
    atr_idx = _index_at_close_time(bars, dt.time(9, 14))
    if atr_idx is None:
        return None
    atr = _atr_at_index(bars, atr_idx)
    if gap_pts < tuning.gap_k_atr * atr:
        return None
    drive_bars = _drive_window_bars(bars)
    if not _retrace_ok(
        gap_pts=gap_pts,
        open_0845=open_0845,
        drive_bars=drive_bars,
        retrace_max_frac=tuning.retrace_max_frac,
    ):
        return None
    if not drive_bars:
        return None
    drive_high = max(float(b.High) for b in drive_bars)
    drive_low = min(float(b.Low) for b in drive_bars)
    sess = _session_bars(bars)
    return DayWashContext(
        day=day,
        atr=atr,
        drive_high=drive_high,
        drive_low=drive_low,
        gap_pts=gap_pts,
        open_0845=open_0845,
        prior_close=prior_close,
        ticks=ticks,
        session_bars=sess,
    )


def _scan_wash_timeline(ctx: DayWashContext, tuning: WashProbeTuning) -> None:
    """Populate break / wash / flow_turn / reclaim on ``ctx`` (mutates)."""
    break_start, deadline = _break_window_ts(ctx.day)
    flow = RollingFlowWindow(FLOW_WINDOW_SEC)
    flow_prev_br: float | None = None
    wash_low = ctx.drive_high
    was_below = False

    for ts, price, vol, tt in ctx.ticks:
        if ts < break_start:
            continue
        if ts > deadline:
            break
        flow.push(ts, vol, tt)
        br = flow.buy_ratio

        if price < ctx.drive_high:
            was_below = True
            wash_low = min(wash_low, price)
            ctx.wash_low = wash_low
            ctx.wash_low_ts = ts
        elif price >= ctx.drive_high:
            if ctx.first_break_ts is None and price > ctx.drive_high:
                ctx.first_break_ts = ts
            if was_below and ctx.reclaim_ts is None:
                ctx.reclaim_ts = ts
                if flow_prev_br is not None:
                    ctx.delta_br_at_reclaim = round(br - flow_prev_br, 4)
            was_below = False

        depth = ctx.drive_high - wash_low
        if (
            ctx.flow_turn_ts is None
            and depth >= tuning.min_wash_k * ctx.atr
            and br >= tuning.br_min
            and flow_prev_br is not None
            and (br - flow_prev_br) >= tuning.delta_br_min
        ):
            ctx.flow_turn_ts = ts

        flow_prev_br = br


def _detect_entries(ctx: DayWashContext, tuning: WashProbeTuning) -> list[ProbeEntry]:
    _scan_wash_timeline(ctx, tuning)
    break_start, deadline = _break_window_ts(ctx.day)
    flow = RollingFlowWindow(FLOW_WINDOW_SEC)
    flow_prev_br: float | None = None

    p0_done = False
    flow_turn_done = False
    reclaim_done = False
    p0_quality_done = False
    wash_low = ctx.drive_high
    was_below = False
    entries: list[ProbeEntry] = []

    def _append(mode: EntryMode, ts: int, price: float, br: float, dbr: float) -> None:
        depth = max(0.0, ctx.drive_high - wash_low)
        sell_ratio, vol_shrink = _vol_shrink_on_decline(ctx.ticks, ts)
        entries.append(
            ProbeEntry(
                entry_mode=mode,
                entry_ts=ts,
                entry_price=price,
                br_at_entry=round(br, 4),
                delta_br_at_entry=round(dbr, 4),
                sell_ratio_at_entry=round(sell_ratio, 4),
                wash_depth=round(depth, 2),
                dip_below_dh=price < ctx.drive_high or depth > 0,
                vol_shrink_on_wash=vol_shrink,
            )
        )

    for ts, price, vol, tt in ctx.ticks:
        if ts < break_start:
            continue
        if ts > deadline:
            break
        flow.push(ts, vol, tt)
        br = flow.buy_ratio
        dbr = (br - flow_prev_br) if flow_prev_br is not None else 0.0

        if price < ctx.drive_high:
            was_below = True
            wash_low = min(wash_low, price)

        depth = ctx.drive_high - wash_low
        if (
            not flow_turn_done
            and depth >= tuning.min_wash_k * ctx.atr
            and br >= tuning.br_min
            and dbr >= tuning.delta_br_min
        ):
            _append("flow_turn", ts, price, br, dbr)
            flow_turn_done = True

        if not p0_done and price > ctx.drive_high:
            _append("p0", ts, price, br, dbr)
            p0_done = True
            if (
                not p0_quality_done
                and (price - ctx.drive_high) >= tuning.break_eps * ctx.atr
                and br >= tuning.br_min
            ):
                _append("p0_quality", ts, price, br, dbr)
                p0_quality_done = True

        if price >= ctx.drive_high and was_below and not reclaim_done and dbr >= tuning.delta_br_min:
            _append("reclaim_br", ts, price, br, dbr)
            reclaim_done = True
            was_below = False

        flow_prev_br = br

    return entries


def _stop_less(
    entry: ProbeEntry,
    ctx: DayWashContext,
    window_sec: int,
) -> float:
    from reporting.forward_pnl import TickSeries

    series = TickSeries(
        timestamps=[t[0] for t in ctx.ticks],
        closes=[t[1] for t in ctx.ticks],
    )
    stats = entry_window_stats(
        entry.entry_price,
        entry.entry_ts,
        "Long",
        series,
        window_sec,
        atr=ctx.atr,
    )
    return float(stats["close_delta"])


def _path_mfe_mae(
    entry: ProbeEntry, ctx: DayWashContext, horizon_sec: int = 3600
) -> tuple[float, float, bool]:
    sign = 1.0
    mfe = 0.0
    mae = 0.0
    end_ts = entry.entry_ts + horizon_sec
    dipped = False
    for ts, price, _, _ in ctx.ticks:
        if ts < entry.entry_ts:
            continue
        if ts > end_ts:
            break
        if price < ctx.drive_high:
            dipped = True
        delta = sign * (price - entry.entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
    return mfe, mae, dipped


def classify_wash_label(
    *,
    entry: ProbeEntry,
    ctx: DayWashContext,
    w15: float,
    w30: float,
    w60: float,
    mfe: float,
    mae: float,
    dipped_below_dh: bool,
    friction: float = FRICTION_POINTS,
) -> WashLabel:
    """Post-hoc wash label per FT-018b plan §1."""
    if not dipped_below_dh and entry.entry_ts - int(
        dt.datetime.combine(ctx.day, BREAK_START).timestamp()
    ) <= 90:
        return "momentum_clean"
    if mfe >= 0.5 * ctx.atr:
        return "momentum_clean"
    if dipped_below_dh:
        if w30 <= 0 and mae > mfe:
            return "wash_real"
        reclaim_dbr = ctx.delta_br_at_reclaim or 0.0
        if w30 > friction and (reclaim_dbr >= 0.05 or w60 > w15):
            return "wash_fake"
    return "ambiguous"


def _price_at_ts(
    ticks: list[tuple[int, float, int, int]],
    ts: int,
    default: float,
) -> float:
    px = default
    for tick_ts, price, _, _ in ticks:
        if tick_ts <= ts:
            px = price
        else:
            break
    return px


def simulate_flow_bailout_exit(
    *,
    entry_price: float,
    entry_ts: int,
    atr: float,
    ticks: list[tuple[int, float, int, int]],
    initial_stop_price: float,
    flow_window_sec: int = FLOW_WINDOW_SEC,
    e1_sec: int = FLOW_BAILOUT_E1_SEC,
    e2_sec: int = FLOW_BAILOUT_E2_SEC,
    br3_sec: int = FLOW_BAILOUT_BR3_SEC,
    e1_atr_k: float = FLOW_BAILOUT_E1_ATR_K,
    e1_br_max: float = FLOW_BAILOUT_E1_BR_MAX,
    e2_slope_min: float = FLOW_BAILOUT_E2_SLOPE_MIN,
    handoff_mfe_atr_k: float = FLOW_BAILOUT_HANDOFF_MFE_ATR_K,
    max_hold_sec: int = SEALED_MAX_HOLD,
    min_atr_pts: float = 25.0,
) -> dict[str, Any]:
    """E1/E2 flow checkpoints + drive_low floor; sealed trail after ``handoff_mfe_atr_k`` MFE."""
    atr_eff = max(atr, min_atr_pts) if atr > 0 else min_atr_pts
    flow = RollingFlowWindow(flow_window_sec)
    mfe = 0.0
    mae = 0.0
    peak = entry_price
    effective_stop = initial_stop_price
    br3: float | None = None
    br5: float | None = None
    br10: float | None = None
    px5: float | None = None
    px10: float | None = None
    done5 = False
    done10 = False
    handoff = False
    be_armed = False
    trail_armed = False
    end_ts = entry_ts + max_hold_sec
    last_price = entry_price
    last_ts = entry_ts

    def _payload(gross: float, *, exit_reason: str, hold_sec: int, exit_price: float) -> dict[str, Any]:
        return {
            "gross_pnl": round(gross, 2),
            "exit_reason": exit_reason,
            "hold_sec": hold_sec,
            "exit_price": round(exit_price, 2),
            "mfe": round(mfe, 2),
            "mae": round(mae, 2),
            "be_armed": be_armed,
            "trail_armed": trail_armed,
        }

    for ts, price, vol, tick_type in ticks:
        if ts < entry_ts:
            continue
        if ts > end_ts:
            break

        flow.push(ts, vol, tick_type)
        br = flow.buy_ratio
        since = ts - entry_ts
        last_price = price
        last_ts = ts
        delta = price - entry_price
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
        peak = max(peak, price)

        if mfe >= handoff_mfe_atr_k * atr_eff:
            handoff = True

        if not handoff:
            if since >= br3_sec and br3 is None:
                br3 = br
            if since >= e1_sec and br5 is None:
                br5 = br
                px5 = price - entry_price
            if since >= e2_sec and br10 is None:
                br10 = br
                px10 = price - entry_price
            if not done5 and since >= e1_sec:
                done5 = True
                if (
                    px5 is not None
                    and px5 < -e1_atr_k * atr_eff
                    and br5 is not None
                    and br5 < e1_br_max
                ):
                    exit_px = _price_at_ts(ticks, entry_ts + e1_sec, price)
                    return _payload(
                        exit_px - entry_price,
                        exit_reason="flow_bailout_e1",
                        hold_sec=e1_sec,
                        exit_price=exit_px,
                    )
            if not done10 and since >= e2_sec:
                done10 = True
                slope = (br10 - br3) if br10 is not None and br3 is not None else 0.0
                if (
                    px10 is not None
                    and px10 < 0
                    and slope < e2_slope_min
                ):
                    exit_px = _price_at_ts(ticks, entry_ts + e2_sec, price)
                    return _payload(
                        exit_px - entry_price,
                        exit_reason="flow_bailout_e2",
                        hold_sec=e2_sec,
                        exit_price=exit_px,
                    )

        if handoff:
            fav = peak - entry_price
            if fav >= SEALED_BE * atr_eff:
                be_armed = True
                effective_stop = max(effective_stop, entry_price)
            if fav >= SEALED_TRAIL_ARM * atr_eff:
                trail_armed = True
            if trail_armed:
                effective_stop = max(effective_stop, peak - SEALED_TRAIL_DIST * atr_eff)
            if SEALED_HARD_TP is not None and fav >= SEALED_HARD_TP * atr_eff:
                tp_price = entry_price + SEALED_HARD_TP * atr_eff
                return _payload(
                    SEALED_HARD_TP * atr_eff,
                    exit_reason="take_profit",
                    hold_sec=ts - entry_ts,
                    exit_price=tp_price,
                )

        if price <= effective_stop:
            reason = "trail_stop" if trail_armed else "stop_loss"
            if be_armed and abs(effective_stop - entry_price) < 0.01:
                reason = "breakeven"
            return _payload(
                effective_stop - entry_price,
                exit_reason=reason,
                hold_sec=ts - entry_ts,
                exit_price=effective_stop,
            )

    return _payload(
        last_price - entry_price,
        exit_reason="horizon",
        hold_sec=max(0, last_ts - entry_ts),
        exit_price=last_price,
    )


def simulate_conditional_break_dl_exit(
    *,
    entry_price: float,
    entry_ts: int,
    atr: float,
    ticks: list[tuple[int, float, int, int]],
    drive_low: float,
    first_break_ts: int | None,
    hard_stop_atr_k: float = SEALED_K_SL,
    trail_arm_atr_k: float = SEALED_TRAIL_ARM,
    trail_dist_atr_k: float = SEALED_TRAIL_DIST,
    hard_tp_atr_k: float | None = SEALED_HARD_TP,
    max_hold_sec: int = SEALED_MAX_HOLD,
    min_atr_pts: float = 25.0,
) -> dict[str, Any]:
    """Pre-break: ATR hard stop only; at/after ``first_break_ts``: floor at ``drive_low−2``.

    Lets early ``flow_turn`` survive drive-low retests before DH break; tightens once
    continuation is confirmed.
    """
    atr_eff = max(atr, min_atr_pts) if atr > 0 else min_atr_pts
    struct_stop = drive_low - WASH_STOP_BUFFER
    effective_stop = entry_price - hard_stop_atr_k * atr_eff
    peak = entry_price
    be_armed = False
    trail_armed = False
    end_ts = entry_ts + max_hold_sec
    mfe = 0.0
    mae = 0.0
    last_price = entry_price
    last_ts = entry_ts

    def _payload(gross: float, *, exit_reason: str, hold_sec: int, exit_price: float) -> dict[str, Any]:
        return {
            "gross_pnl": round(gross, 2),
            "exit_reason": exit_reason,
            "hold_sec": hold_sec,
            "exit_price": round(exit_price, 2),
            "mfe": round(mfe, 2),
            "mae": round(mae, 2),
            "be_armed": be_armed,
            "trail_armed": trail_armed,
        }

    for ts, price, _vol, _tt in ticks:
        if ts < entry_ts:
            continue
        if ts > end_ts:
            break

        last_price = price
        last_ts = ts
        delta = price - entry_price
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
        peak = max(peak, price)

        if first_break_ts is not None and ts >= first_break_ts:
            effective_stop = max(effective_stop, struct_stop)

        fav = peak - entry_price
        if fav >= trail_arm_atr_k * atr_eff:
            trail_armed = True
        if trail_armed:
            effective_stop = max(effective_stop, peak - trail_dist_atr_k * atr_eff)

        if price <= effective_stop:
            gross = effective_stop - entry_price
            if trail_armed:
                reason = "trail_stop"
            else:
                reason = "stop_loss"
            return _payload(gross, exit_reason=reason, hold_sec=ts - entry_ts, exit_price=effective_stop)

        if hard_tp_atr_k is not None and fav >= hard_tp_atr_k * atr_eff:
            tp_price = entry_price + hard_tp_atr_k * atr_eff
            return _payload(
                hard_tp_atr_k * atr_eff,
                exit_reason="take_profit",
                hold_sec=ts - entry_ts,
                exit_price=tp_price,
            )

    gross = last_price - entry_price
    return _payload(
        gross,
        exit_reason="horizon",
        hold_sec=max(0, last_ts - entry_ts),
        exit_price=last_price,
    )


def _resolve_stop_price(
    entry: ProbeEntry,
    ctx: DayWashContext,
    exit_mode: ExitMode,
) -> float | None:
    depth = entry.wash_depth
    atr_stop = entry.entry_price - SEALED_K_SL * ctx.atr
    if exit_mode == "sealed":
        return None
    if exit_mode in ("drive_low_struct", "flow_bailout"):
        return ctx.drive_low - WASH_STOP_BUFFER
    if ctx.wash_low is not None:
        wash_stop = ctx.wash_low - WASH_STOP_BUFFER
        if depth >= WASH_STRUCT_DEPTH_K * ctx.atr:
            if exit_mode in ("momentum_tail", "momentum_tail_trail"):
                return min(wash_stop, atr_stop)
            return wash_stop
    return None


def _simulate_exit(
    entry: ProbeEntry,
    ctx: DayWashContext,
    exit_mode: ExitMode,
) -> dict[str, Any]:
    initial_stop = _resolve_stop_price(entry, ctx, exit_mode)
    if exit_mode == "sealed":
        return simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=SEALED_K_SL,
            be_trigger_atr_k=SEALED_BE,
            trail_arm_atr_k=SEALED_TRAIL_ARM,
            trail_dist_atr_k=SEALED_TRAIL_DIST,
            hard_tp_atr_k=SEALED_HARD_TP,
            max_hold_sec=SEALED_MAX_HOLD,
        )
    if exit_mode == "wash_struct":
        return simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=SEALED_K_SL,
            be_trigger_atr_k=None,
            trail_arm_atr_k=SEALED_TRAIL_ARM,
            trail_dist_atr_k=SEALED_TRAIL_DIST,
            hard_tp_atr_k=SEALED_HARD_TP,
            max_hold_sec=SEALED_MAX_HOLD,
            initial_stop_price=initial_stop,
        )
    if exit_mode == "drive_low_struct":
        return simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=SEALED_K_SL,
            be_trigger_atr_k=None,
            trail_arm_atr_k=SEALED_TRAIL_ARM,
            trail_dist_atr_k=SEALED_TRAIL_DIST,
            hard_tp_atr_k=SEALED_HARD_TP,
            max_hold_sec=SEALED_MAX_HOLD,
            initial_stop_price=initial_stop,
        )
    if exit_mode == "flow_bailout":
        assert initial_stop is not None
        return simulate_flow_bailout_exit(
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            initial_stop_price=initial_stop,
        )
    if exit_mode == "momentum_tail":
        return simulate_atr_trail_skew_exit(
            direction="Long",
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            hard_stop_atr_k=SEALED_K_SL,
            be_trigger_atr_k=None,
            trail_arm_atr_k=SEALED_TRAIL_ARM,
            trail_dist_atr_k=SEALED_TRAIL_DIST,
            hard_tp_atr_k=SEALED_HARD_TP,
            max_hold_sec=1800,
            initial_stop_price=initial_stop,
        )
    # momentum_tail_trail
    return simulate_atr_trail_skew_exit(
        direction="Long",
        entry_price=entry.entry_price,
        entry_ts=entry.entry_ts,
        atr=ctx.atr,
        ticks=ctx.ticks,
        hard_stop_atr_k=SEALED_K_SL,
        be_trigger_atr_k=None,
        trail_arm_atr_k=SEALED_TRAIL_ARM,
        trail_dist_atr_k=SEALED_TRAIL_DIST,
        hard_tp_atr_k=None,
        max_hold_sec=1800,
        initial_stop_price=initial_stop,
    )


def probe_day_rows(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    sorted_dates: list[dt.date],
    tuning: WashProbeTuning | None = None,
    friction: float = FRICTION_POINTS,
) -> list[dict[str, Any]]:
    tuning = tuning or WashProbeTuning()
    ctx = _load_day_context(code, day, cache_dir=cache_dir, sorted_dates=sorted_dates, tuning=tuning)
    if ctx is None:
        return []
    entries = _detect_entries(ctx, tuning)
    if not entries:
        return []

    rows: list[dict[str, Any]] = []
    for entry in entries:
        mfe, mae, dipped = _path_mfe_mae(entry, ctx)
        w15 = _stop_less(entry, ctx, 900)
        w30 = _stop_less(entry, ctx, 1800)
        w60 = _stop_less(entry, ctx, 3600)
        label = classify_wash_label(
            entry=entry,
            ctx=ctx,
            w15=w15,
            w30=w30,
            w60=w60,
            mfe=mfe,
            mae=mae,
            dipped_below_dh=dipped or entry.dip_below_dh,
            friction=friction,
        )
        for exit_mode in EXIT_MODES:
            sim = _simulate_exit(entry, ctx, exit_mode)
            gross = float(sim["gross_pnl"])
            rows.append(
                {
                    "day": day.isoformat(),
                    "entry_mode": entry.entry_mode,
                    "exit_mode": exit_mode,
                    "entry_ts": entry.entry_ts,
                    "entry_px": round(entry.entry_price, 1),
                    "atr": round(ctx.atr, 2),
                    "net": round(gross - friction, 2),
                    "gross": round(gross, 2),
                    "exit_reason": sim["exit_reason"],
                    "wash_label": label,
                    "w15": round(w15, 2),
                    "w30": round(w30, 2),
                    "w60": round(w60, 2),
                    "dip_depth": entry.wash_depth,
                    "mfe": round(mfe, 2),
                    "mae": round(mae, 2),
                    "br": entry.br_at_entry,
                    "delta_br": entry.delta_br_at_entry,
                    "sell_ratio": entry.sell_ratio_at_entry,
                    "vol_shrink": entry.vol_shrink_on_wash,
                    "drive_high": round(ctx.drive_high, 1),
                    "drive_low": round(ctx.drive_low, 1),
                    "open_0845": round(ctx.open_0845, 1),
                }
            )
    return rows


def run_probe_range(
    *,
    code: str,
    from_date: str,
    to_date: str,
    cache_dir: Path,
    tuning: WashProbeTuning | None = None,
) -> list[dict[str, Any]]:
    dates = resolve_cli_tick_cache_dates(
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        explicit=None,
        from_cache=True,
    )
    tuning = tuning or WashProbeTuning()
    all_rows: list[dict[str, Any]] = []
    for day in dates:
        all_rows.extend(
            probe_day_rows(code, day, cache_dir=cache_dir, sorted_dates=dates, tuning=tuning)
        )
    return all_rows


def read_probe_csv(path: Path) -> list[dict[str, Any]]:
    """Load probe matrix rows written by ``write_probe_csv``."""
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_probe_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _day_panel_section(day: str, rows: list[dict[str, Any]]) -> list[str]:
    day_rows = [r for r in rows if r["day"] == day]
    if not day_rows:
        return [f"## {day}", "", "*No GUDT qualifying day / no entries*", ""]
    label = day_rows[0]["wash_label"]
    sealed_p0 = next(
        (r for r in day_rows if r["entry_mode"] == "p0" and r["exit_mode"] == "sealed"),
        None,
    )
    ft_ws = next(
        (r for r in day_rows if r["entry_mode"] == "flow_turn" and r["exit_mode"] == "wash_struct"),
        None,
    )
    ft_dl = next(
        (r for r in day_rows if r["entry_mode"] == "flow_turn" and r["exit_mode"] == "drive_low_struct"),
        None,
    )
    best = max(day_rows, key=lambda r: float(r["net"]))
    lines = [
        f"## {day}",
        "",
        f"- wash_label (p0 path): `{label}`",
        f"- drive_high: {day_rows[0].get('drive_high', '—')} · drive_low: {day_rows[0].get('drive_low', '—')}",
        "",
        "| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |",
        "|-------|------|-----|-------------|-----|-----|------------|------------|",
    ]
    for r in sorted(day_rows, key=lambda x: (-float(x["net"]), x["entry_mode"], x["exit_mode"])):
        lines.append(
            f"| {r['entry_mode']} | {r['exit_mode']} | {r['net']} | {r['exit_reason']} | "
            f"{r['w30']} | {r['w60']} | {r.get('sell_ratio', '—')} | {r.get('vol_shrink', '—')} |"
        )
    lines.append("")
    if ft_ws:
        lines.append(
            f"- flow_turn+wash_struct: net={ft_ws['net']} · dBR={ft_ws.get('delta_br')} · "
            f"depth={ft_ws.get('dip_depth')}"
        )
    if ft_dl:
        lines.append(f"- flow_turn+drive_low_struct: net={ft_dl['net']}")
    if sealed_p0:
        delta = round(float(best["net"]) - float(sealed_p0["net"]), 2)
        lines.append(
            f"**Best** `{best['entry_mode']}+{best['exit_mode']}` net={best['net']} "
            f"vs sealed p0={sealed_p0['net']} (Δ={delta})"
        )
    else:
        lines.append(f"**Best** `{best['entry_mode']}+{best['exit_mode']}` net={best['net']}")
    lines.append("")
    return lines


def format_panel_md(
    rows: list[dict[str, Any]],
    *,
    panel_days: tuple[str, ...] = PANEL_DAYS_DEFAULT,
) -> str:
    lines = [
        "# GUDT Wash Probe — Panel",
        "",
        "Exploratory FT-018b · does not overwrite sealed baseline.",
        "",
    ]
    for day in panel_days:
        lines.extend(_day_panel_section(day, rows))

    # Summary vs sealed p0
    p0_sealed = [r for r in rows if r["entry_mode"] == "p0" and r["exit_mode"] == "sealed"]
    if p0_sealed:
        total_sealed = sum(float(r["net"]) for r in p0_sealed)
        lines.extend(
            [
                "## Panel aggregate (p0+sealed)",
                "",
                f"- days: {len(p0_sealed)} · net_total: {round(total_sealed, 2)}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _row_for(rows: list[dict[str, Any]], entry_mode: str, exit_mode: str) -> dict[str, Any] | None:
    return next(
        (r for r in rows if r["entry_mode"] == entry_mode and r["exit_mode"] == exit_mode),
        None,
    )


def _px_at_tick(
    ticks: list[tuple[int, float, int, int]],
    ts: int,
    default: float,
) -> float:
    px = default
    for tick_ts, price, _, _ in ticks:
        if tick_ts <= ts:
            px = price
        else:
            break
    return px


def _vol_br_at(
    ticks: list[tuple[int, float, int, int]],
    end_ts: int,
    *,
    window_sec: int = FLOW_WINDOW_SEC,
) -> float:
    buy = total = 0
    for tick_ts, _, vol, tick_type in ticks:
        if end_ts - window_sec < tick_ts <= end_ts:
            total += vol
            if tick_type == 1:
                buy += vol
    return buy / total if total else 0.5


def distribution_confirm_metrics(
    signal: DistributionSignal,
    p0_row: dict[str, Any],
    ctx: DayWashContext,
    *,
    params: DistributionHedgeParams,
) -> dict[str, float] | None:
    """ATR-scaled dump + 2m follow-through at ``signal + confirm_sec``."""
    if params.confirm_sec <= 0:
        return None
    atr = float(p0_row.get("atr") or ctx.atr)
    if atr <= 0:
        return None
    confirm_ts = signal.flip_ts + params.confirm_sec
    confirm_px = _px_at_tick(ctx.ticks, confirm_ts, signal.flip_px)
    dump_atr = (signal.flip_px - signal.p0_entry_px) / atr
    slope2_atr = (confirm_px - signal.flip_px) / atr
    return {
        "dump_atr": round(dump_atr, 4),
        "slope2_atr": round(slope2_atr, 4),
        "confirm_ts": float(confirm_ts),
        "confirm_px": confirm_px,
    }


def distribution_confirm_pass(
    signal: DistributionSignal,
    p0_row: dict[str, Any],
    ctx: DayWashContext,
    *,
    params: DistributionHedgeParams,
) -> tuple[bool, dict[str, float] | None]:
    """True when phase-2 confirm passes (or confirm disabled)."""
    if params.confirm_sec <= 0 or params.confirm_min_dump_atr is None:
        return True, None
    metrics = distribution_confirm_metrics(signal, p0_row, ctx, params=params)
    if metrics is None:
        return False, None
    lo = params.confirm_slope2_min if params.confirm_slope2_min is not None else -999.0
    hi = params.confirm_slope2_max if params.confirm_slope2_max is not None else 999.0
    ok = (
        metrics["dump_atr"] <= -params.confirm_min_dump_atr
        and lo <= metrics["slope2_atr"] <= hi
    )
    return ok, metrics


def distribution_signal_at_p0(
    p0_row: dict[str, Any],
    ctx: DayWashContext,
    *,
    params: DistributionHedgeParams | None = None,
) -> DistributionSignal | None:
    """P0 + delay: px below P0 entry and BR below threshold → distribution flip."""
    params = params or DistributionHedgeParams()
    p0_ts = int(p0_row["entry_ts"])
    p0_px = float(p0_row["entry_px"])
    flip_ts = p0_ts + params.signal_delay_sec
    flip_px = _px_at_tick(ctx.ticks, flip_ts, p0_px)
    br = _vol_br_at(ctx.ticks, flip_ts)
    if flip_px < p0_px and br < params.br_max:
        return DistributionSignal(
            flip_ts=flip_ts,
            flip_px=flip_px,
            br_at_flip=round(br, 4),
            p0_entry_px=p0_px,
        )
    return None


def simulate_short_to_stop(
    ticks: list[tuple[int, float, int, int]],
    *,
    entry_ts: int,
    entry_px: float,
    stop_px: float,
    max_hold_sec: int,
) -> dict[str, Any]:
    """Short leg with fixed stop above entry; positive gross_pnl when price falls."""
    end_ts = entry_ts + max_hold_sec
    last_px = entry_px
    last_ts = entry_ts
    for tick_ts, price, _, _ in ticks:
        if tick_ts < entry_ts:
            continue
        last_px = price
        last_ts = tick_ts
        if tick_ts > end_ts:
            break
        if price >= stop_px:
            return {
                "gross_pnl": entry_px - stop_px,
                "exit_reason": "stop_loss",
                "hold_sec": tick_ts - entry_ts,
                "exit_price": stop_px,
            }
    return {
        "gross_pnl": entry_px - last_px,
        "exit_reason": "horizon",
        "hold_sec": max(0, last_ts - entry_ts),
        "exit_price": last_px,
    }


def _long_row_for_pick(
    day_rows: list[dict[str, Any]],
    pick: dict[str, Any],
) -> dict[str, Any] | None:
    path = pick["path"]
    if path.startswith("flow_turn"):
        exit_mode = "drive_low_struct" if "drive_low" in path else "flow_bailout"
        return _row_for(day_rows, "flow_turn", exit_mode) or _row_for(
            day_rows, "flow_turn", "drive_low_struct"
        )
    if path.startswith("p0") or path.startswith("reclaim_br"):
        em = "p0" if path.startswith("p0") else "reclaim_br"
        ex = "sealed" if em == "p0" else "wash_struct"
        return _row_for(day_rows, em, ex)
    return None


def apply_hedge_distribution_short(
    pick: dict[str, Any],
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: DistributionHedgeParams | None = None,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any]:
    """B' long pick + optional flip: exit long at distribution signal, enter short."""
    params = params or DistributionHedgeParams()
    p0 = _row_for(day_rows, "p0", "sealed")
    out = dict(pick)
    out["hedge"] = "none"
    out["long_net"] = pick["net"]
    out["short_net"] = 0.0

    if p0 is None:
        return out

    signal = distribution_signal_at_p0(p0, ctx, params=params)
    if signal is None:
        return out

    long_row = _long_row_for_pick(day_rows, pick)
    if long_row is None:
        return out

    confirm_ok, confirm_m = distribution_confirm_pass(signal, p0, ctx, params=params)
    if not confirm_ok:
        out["dist_confirm"] = "veto"
        if confirm_m:
            out["dump_atr"] = confirm_m["dump_atr"]
            out["slope2_atr"] = confirm_m["slope2_atr"]
        return out

    long_entry_px = float(long_row["entry_px"])
    long_gross = signal.flip_px - long_entry_px
    long_net = long_gross - friction

    stop_px = float(p0["drive_high"]) + params.short_stop_pts
    if confirm_m is not None:
        short_entry_ts = int(confirm_m["confirm_ts"])
        short_entry_px = float(confirm_m["confirm_px"])
        out["dist_confirm"] = "pass"
        out["dump_atr"] = confirm_m["dump_atr"]
        out["slope2_atr"] = confirm_m["slope2_atr"]
    else:
        short_entry_ts = signal.flip_ts
        short_entry_px = signal.flip_px
    short_sim = simulate_short_to_stop(
        ctx.ticks,
        entry_ts=short_entry_ts,
        entry_px=short_entry_px,
        stop_px=stop_px,
        max_hold_sec=params.short_max_hold_sec,
    )
    short_net = float(short_sim["gross_pnl"]) - friction

    out.update({
        "hedge": "flip",
        "net": round(long_net + short_net, 2),
        "long_net": round(long_net, 2),
        "short_net": round(short_net, 2),
        "exit_reason": f"dist_flip:{short_sim['exit_reason']}",
        "dist_br": signal.br_at_flip,
        "dist_flip_ts": signal.flip_ts,
        "dist_short_ts": short_entry_ts,
    })
    return out


def load_probe_contexts(
    code: str,
    days: list[str],
    *,
    cache_dir: Path,
    tuning: WashProbeTuning | None = None,
) -> dict[str, DayWashContext]:
    """Load ``DayWashContext`` (with wash timeline) for hedge replay."""
    if not days:
        return {}
    tuning = tuning or WashProbeTuning()
    lo = min(days)
    pad_from = (dt.date.fromisoformat(lo) - dt.timedelta(days=45)).isoformat()
    hi = max(days)
    dates = resolve_cli_tick_cache_dates(
        code=code,
        cache_dir=cache_dir,
        from_date=pad_from,
        to_date=hi,
        explicit=None,
        from_cache=True,
    )
    out: dict[str, DayWashContext] = {}
    for day_s in days:
        day = dt.date.fromisoformat(day_s)
        ctx = _load_day_context(code, day, cache_dir=cache_dir, sorted_dates=dates, tuning=tuning)
        if ctx is not None:
            _scan_wash_timeline(ctx, tuning)
            out[day_s] = ctx
    return out


def summarize_rule_with_distribution_hedge(
    rows: list[dict[str, Any]],
    *,
    rule: Literal["B", "B_prime", "D"] = "B_prime",
    ft_exit: ExitMode = "drive_low_struct",
    ctx_by_day: dict[str, DayWashContext],
    params: DistributionHedgeParams | None = None,
) -> dict[str, Any]:
    """Aggregate rule picks with ``hedge_distribution_short`` flip leg."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    picks: list[dict[str, Any]] = []
    for day_rows in by_day.values():
        base = rule_pick_for_day(day_rows, rule=rule, ft_exit=ft_exit)
        if base is None:
            continue
        day = base["day"]
        ctx = ctx_by_day.get(day)
        if ctx is None:
            picks.append({**base, "hedge": "none", "long_net": base["net"], "short_net": 0.0})
            continue
        picks.append(apply_hedge_distribution_short(base, day_rows, ctx, params=params))
    nets = [float(p["net"]) for p in picks]
    hedge_days = sum(1 for p in picks if p.get("hedge") == "flip")
    return {
        "rule": rule,
        "ft_exit": ft_exit,
        "hedge": "distribution_short",
        "n": len(picks),
        "hedge_days": hedge_days,
        "ft_days": sum(
            1
            for p in picks
            if p["path"].startswith("flow_turn") or p["path"] == "reclaim_br+wash_struct"
        ),
        "veto_days": sum(1 for p in picks if "veto" in p["path"]),
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1) if nets else 0.0,
        "picks": picks,
    }


def pre_break_br_at(
    ctx: DayWashContext,
    *,
    lookback_sec: int = 300,
) -> float | None:
    """Buy ratio in ``lookback_sec`` window ending at first break of ``drive_high``."""
    if ctx.first_break_ts is None:
        return None
    return _vol_br_at(ctx.ticks, ctx.first_break_ts - lookback_sec)


def ext_open_atr(ctx: DayWashContext) -> float:
    """(drive_high − open_0845) / ATR — chase extension before break."""
    if ctx.atr <= 0:
        return 0.0
    return (ctx.drive_high - ctx.open_0845) / ctx.atr


def ext_open_atr_for_day(
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext | None = None,
) -> float | None:
    """``ext_open_atr`` from ctx or probe row fields."""
    if ctx is not None:
        return ext_open_atr(ctx)
    if not day_rows:
        return None
    r = day_rows[0]
    atr = float(r.get("atr") or 0)
    if atr <= 0 or "open_0845" not in r:
        return None
    return (float(r["drive_high"]) - float(r["open_0845"])) / atr


def sess_vwap_dist_atr(
    ctx: DayWashContext,
    entry_px: float,
    *,
    session_bars: list[Any] | None = None,
) -> float | None:
    """(entry − session_vwap_at_break) / ATR; requires 1m bars through 09:45."""
    if ctx.atr <= 0 or session_bars is None:
        return None
    vwaps = _session_vwap_series(session_bars)
    idx = _index_at_close_time(session_bars, BREAK_START)
    if idx is None:
        return None
    return (entry_px - vwaps[idx]) / ctx.atr


def build_session_bars_by_day(
    code: str,
    days: list[str],
    *,
    cache_dir: Path,
    ctx_by_day: dict[str, DayWashContext] | None = None,
) -> dict[str, list[Any]]:
    """Session 1m bars for chase / VWAP metrics (reuse probe ctx when available)."""
    if ctx_by_day:
        return {
            d: ctx.session_bars
            for d, ctx in ctx_by_day.items()
            if ctx.session_bars is not None
        }
    out: dict[str, list[Any]] = {}
    for day_s in days:
        day = dt.date.fromisoformat(day_s)
        pad = (day - dt.timedelta(days=45)).isoformat()
        dates = resolve_cli_tick_cache_dates(
            code=code,
            cache_dir=cache_dir,
            from_date=pad,
            to_date=day_s,
            explicit=None,
            from_cache=True,
        )
        bundle = _load_gdc_day_context(code, day, cache_dir=cache_dir, sorted_dates=dates)
        if bundle is None:
            continue
        bars, _, _ = bundle
        if bars:
            out[day_s] = _session_bars(bars)
    return out


def _p0_chase_veto(
    pick: dict[str, Any],
    ctx: DayWashContext,
    day_rows: list[dict[str, Any]],
    *,
    params: BPrimeCompositeParams,
    session_bars: list[Any] | None,
) -> bool:
    if not pick["path"].startswith("p0"):
        return False
    if params.p0_ext_open_max is not None and ext_open_atr(ctx) > params.p0_ext_open_max:
        return True
    if params.p0_sess_vwap_dist_max is not None and session_bars is not None:
        p0 = _row_for(day_rows, "p0", "sealed")
        if p0 is None:
            return False
        sv = sess_vwap_dist_atr(ctx, float(p0["entry_px"]), session_bars=session_bars)
        if sv is not None and sv > params.p0_sess_vwap_dist_max:
            return True
    return False


def simulate_distribution_short_leg(
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: DistributionHedgeParams | None = None,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any] | None:
    """Short-only: P0+10m distribution signal → enter short (second leg)."""
    params = params or DistributionHedgeParams()
    p0 = _row_for(day_rows, "p0", "sealed")
    if p0 is None:
        return None
    signal = distribution_signal_at_p0(p0, ctx, params=params)
    if signal is None:
        return None
    stop_px = float(p0["drive_high"]) + params.short_stop_pts
    short_sim = simulate_short_to_stop(
        ctx.ticks,
        entry_ts=signal.flip_ts,
        entry_px=signal.flip_px,
        stop_px=stop_px,
        max_hold_sec=params.short_max_hold_sec,
    )
    short_net = float(short_sim["gross_pnl"]) - friction
    return {
        "day": day_rows[0]["day"],
        "path": "distribution_short",
        "net": round(short_net, 2),
        "short_net": round(short_net, 2),
        "long_net": 0.0,
        "hedge": "short_only",
        "exit_reason": f"dist_short:{short_sim['exit_reason']}",
        "dist_br": signal.br_at_flip,
        "dist_flip_ts": signal.flip_ts,
        "entry_px": round(signal.flip_px, 1),
        "stop_px": round(stop_px, 1),
    }


def _fallback_ft_from_p0_veto(
    day: str,
    day_rows: list[dict[str, Any]],
    *,
    ft_exit: ExitMode,
    tag: str,
) -> dict[str, Any] | None:
    """When p0 chase is vetoed, use early flow_turn if it exists before p0."""
    ft = _row_for(day_rows, "flow_turn", ft_exit) or _row_for(
        day_rows, "flow_turn", "drive_low_struct"
    )
    p0 = _row_for(day_rows, "p0", "sealed")
    if ft is not None and p0 is not None and int(ft["entry_ts"]) < int(p0["entry_ts"]):
        return {
            "day": day,
            "path": f"flow_turn+{ft['exit_mode']} ({tag})",
            "net": float(ft["net"]),
            "exit_reason": ft.get("exit_reason"),
        }
    return None


def apply_b_prime_composite_day(
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: BPrimeCompositeParams | None = None,
    session_bars: list[Any] | None = None,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any] | None:
    """B′ composite: entry vetoes → long pick → optional distribution flip."""
    params = params or BPrimeCompositeParams()
    day = day_rows[0]["day"]

    if params.pre_break_br_min is not None and not params.pre_break_br_p0_only:
        br5 = pre_break_br_at(ctx)
        if br5 is not None and br5 < params.pre_break_br_min:
            return None

    if params.short_only:
        return simulate_distribution_short_leg(
            day_rows, ctx, params=params.distribution, friction=friction
        )

    base = rule_pick_for_day(day_rows, rule="B_prime", ft_exit=params.ft_exit)
    if base is None:
        return None

    if params.pre_break_br_p0_only and params.pre_break_br_min is not None:
        if base["path"].startswith("p0"):
            br5 = pre_break_br_at(ctx)
            if br5 is not None and br5 < params.pre_break_br_min:
                fb = _fallback_ft_from_p0_veto(
                    day, day_rows, ft_exit=params.ft_exit, tag="br5_veto"
                )
                if fb is None:
                    return None
                base = fb

    bars = session_bars if session_bars is not None else ctx.session_bars
    if _p0_chase_veto(base, ctx, day_rows, params=params, session_bars=bars):
        fb = _fallback_ft_from_p0_veto(
            day, day_rows, ft_exit=params.ft_exit, tag="chase_veto"
        )
        if fb is None:
            return None
        base = fb

    if params.flip_min_ext_open is not None:
        ext = ext_open_atr(ctx)
        if ext is None or ext <= params.flip_min_ext_open:
            out = dict(base)
            out["hedge"] = "none"
            out["long_net"] = float(base["net"])
            out["short_net"] = 0.0
            out["composite"] = "bprime_dist"
            return out

    out = apply_hedge_distribution_short(
        base, day_rows, ctx, params=params.distribution, friction=friction
    )
    out["composite"] = "bprime_dist"
    return out


def summarize_b_prime_composite(
    rows: list[dict[str, Any]],
    *,
    ctx_by_day: dict[str, DayWashContext],
    params: BPrimeCompositeParams | None = None,
    session_bars_by_day: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate ``apply_b_prime_composite_day`` over probe rows."""
    params = params or BPrimeCompositeParams()
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    picks: list[dict[str, Any]] = []
    skipped = 0
    for day_rows in by_day.values():
        day = day_rows[0]["day"]
        ctx = ctx_by_day.get(day)
        if ctx is None:
            continue
        bars = None
        if session_bars_by_day is not None:
            bars = session_bars_by_day.get(day)
        elif params.p0_sess_vwap_dist_max is not None:
            bars = ctx.session_bars
        p = apply_b_prime_composite_day(day_rows, ctx, params=params, session_bars=bars)
        if p is None:
            skipped += 1
            continue
        picks.append(p)
    nets = [float(p["net"]) for p in picks]
    flip_days = sum(1 for p in picks if p.get("hedge") == "flip")
    short_days = sum(1 for p in picks if p.get("hedge") in ("flip", "short_only"))
    return {
        "composite": "bprime_dist" if not params.short_only else "distribution_short_only",
        "params": params,
        "n": len(picks),
        "skipped_days": skipped,
        "flip_days": flip_days,
        "short_days": short_days,
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1) if nets else 0.0,
        "picks": picks,
    }


def format_b_prime_composite_spec_md() -> str:
    """Human-readable spec for the distribution-short composite."""
    return "\n".join([
        "# B′ Composite — distribution short (second leg)",
        "",
        "## Long leg (B′)",
        "",
        "- `flow_turn_ts < p0_ts` → flow_turn + drive_low_struct; else p0 + sealed",
        "- V10 ft veto unchanged",
        "",
        "## Entry vetoes (optional)",
        "",
        "- **pre_break_br**: skip day if BR at `break_dh − 5min` < 0.35 (v4)",
        "- **pre_break_br_p0_only**: veto p0 pick only; ft winners unaffected (v5)",
        "- **p0_ext_open**: skip p0 chase if `(dh − open) / ATR` > threshold → fallback early ft",
        "- **p0_sess_vwap**: skip p0 chase if `(entry − session_vwap) / ATR` > threshold",
        "- **flip_min_ext_open**: distribution flip only when `(dh − open) / ATR` > threshold",
        "",
        "## Short leg — distribution second leg",
        "",
        f"Anchor: **P0 entry + {DIST_HEDGE_SIGNAL_SEC // 60}min**",
        "",
        "```",
        f"signal = (px < p0_entry) AND (BR < {DIST_HEDGE_BR_MAX})",
        "action: exit long at signal_px; enter short at signal_px",
        f"short_stop = drive_high + {DIST_HEDGE_SHORT_STOP_PTS}",
        "```",
        "",
        "**Short-only mode**: no long; trade only when signal fires.",
        "",
    ]) + "\n"


def format_b_prime_composite_md(
    summary: dict[str, Any],
    *,
    title: str,
    compare_net: float | None = None,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"Composite: `{summary['composite']}` · n={summary['n']} · skipped={summary['skipped_days']} · "
        f"short/flip_days={summary['short_days']} · net={summary['net_total']} · "
        f"mean={summary['net_mean']} · WR={summary['win_rate']}%",
    ]
    if compare_net is not None:
        lines.append(f"- Δ vs B′ alone: {summary['net_total'] - compare_net:+.2f}")
    lines.extend([
        "",
        "| day | path | leg | long | short | net | dist_br |",
        "|-----|------|-----|------|-------|-----|---------|",
    ])
    for p in summary["picks"]:
        leg = p.get("hedge", "—")
        lines.append(
            f"| {p['day']} | {p['path']} | {leg} | {p.get('long_net', 0)} | "
            f"{p.get('short_net', 0)} | {p['net']} | {p.get('dist_br', '—')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _ft_veto_v10(ft_row: dict[str, Any], *, has_p0: bool) -> bool:
    """V10 entry veto: late/deep ft when p0 exists; toxic 1–3 ATR zone when ft-only."""
    day = dt.date.fromisoformat(ft_row["day"])
    break_start = int(dt.datetime.combine(day, BREAK_START).timestamp())
    atr = float(ft_row["atr"])
    if atr <= 0:
        return False
    dist_dh_atr = (float(ft_row["drive_high"]) - float(ft_row["entry_px"])) / atr
    ft_min = (int(ft_row["entry_ts"]) - break_start) / 60.0
    if has_p0:
        return dist_dh_atr > 1.0 and ft_min > 15.0
    return 1.0 < dist_dh_atr < 3.0


def rule_pick_for_day(
    day_rows: list[dict[str, Any]],
    *,
    rule: Literal["B", "B_prime", "D"] = "B",
    ft_exit: ExitMode = "flow_bailout",
    ft_ext_open_min: float | None = None,
    ctx: DayWashContext | None = None,
) -> dict[str, Any] | None:
    """Composite rules over precomputed probe rows.

    ``ft_ext_open_min``: when set (B′ only), veto early ``flow_turn`` if
    ``ext_open_atr > threshold`` and route to ``p0+sealed``.
    """
    ft_dl = _row_for(day_rows, "flow_turn", "drive_low_struct")
    ft = _row_for(day_rows, "flow_turn", ft_exit) or ft_dl
    ft_ts_row = ft_dl or ft
    p0 = _row_for(day_rows, "p0", "sealed")
    reclaim = _row_for(day_rows, "reclaim_br", "wash_struct")

    if ft_ts_row is None and p0 is None:
        return None

    day = day_rows[0]["day"]

    def _pick(row: dict[str, Any], path: str) -> dict[str, Any]:
        return {
            "day": day,
            "path": path,
            "net": float(row["net"]),
            "exit_reason": row.get("exit_reason"),
        }

    if ft is None or p0 is None:
        if rule == "B_prime" and ft is not None and _ft_veto_v10(ft_ts_row or ft, has_p0=p0 is not None):
            return _pick(p0, "p0+sealed (veto)") if p0 else None
        chosen = ft or p0
        if chosen is None:
            return None
        return _pick(chosen, f"{chosen['entry_mode']}+{chosen['exit_mode']}")

    ft_ts = int(ft_ts_row["entry_ts"])
    p0_ts = int(p0["entry_ts"])
    early_ft = ft_ts < p0_ts

    if rule == "D":
        if early_ft and reclaim is not None:
            return _pick(reclaim, "reclaim_br+wash_struct")
        return _pick(p0, "p0+sealed")

    if early_ft:
        if rule == "B_prime" and _ft_veto_v10(ft_ts_row, has_p0=True):
            return _pick(p0, "p0+sealed (veto)")
        if rule == "B_prime" and ft_ext_open_min is not None:
            ext = ext_open_atr_for_day(day_rows, ctx=ctx)
            if ext is not None and ext > ft_ext_open_min:
                return _pick(p0, "p0+sealed (ext_open_veto)")
        return _pick(ft, f"flow_turn+{ft_exit}")

    return _pick(p0, "p0+sealed")


def _probe_entry_from_row(row: dict[str, Any], *, entry_mode: str = "flow_turn") -> ProbeEntry:
    return ProbeEntry(
        entry_mode=entry_mode,  # type: ignore[arg-type]
        entry_ts=int(row["entry_ts"]),
        entry_price=float(row["entry_px"]),
        br_at_entry=float(row.get("br") or row.get("br_at_entry") or 0),
        delta_br_at_entry=float(row.get("delta_br") or row.get("delta_br_at_entry") or 0),
        sell_ratio_at_entry=float(row.get("sell_ratio") or row.get("sell_ratio_at_entry") or 0),
        wash_depth=float(row.get("dip_depth") or row.get("wash_depth") or 0),
        dip_below_dh=bool(row.get("dip_below_dh")),
        vol_shrink_on_wash=bool(row.get("vol_shrink")),
    )


def rule_pick_b_prime_quick_stop_veto(
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext | None,
    *,
    ft_exit: ExitMode = "drive_low_struct",
    quick_stop_max_sec: int = 600,
) -> dict[str, Any] | None:
    """B′ pick with oracle: early ft + dl stop before break within ``quick_stop_max_sec`` → p0."""
    base = rule_pick_for_day(day_rows, rule="B_prime", ft_exit=ft_exit)
    if base is None or ctx is None or not base["path"].startswith("flow_turn"):
        return base

    ft_row = _row_for(day_rows, "flow_turn", ft_exit) or _row_for(
        day_rows, "flow_turn", "drive_low_struct"
    )
    p0 = _row_for(day_rows, "p0", "sealed")
    if ft_row is None or p0 is None:
        return base
    if int(ft_row["entry_ts"]) >= int(p0["entry_ts"]):
        return base

    entry = _probe_entry_from_row(ft_row)
    sim = _simulate_exit(entry, ctx, ft_exit)
    if (
        sim["exit_reason"] == "stop_loss"
        and int(sim["hold_sec"]) <= quick_stop_max_sec
        and ctx.first_break_ts is not None
        and entry.entry_ts < ctx.first_break_ts
    ):
        day = day_rows[0]["day"]
        return {
            "day": day,
            "path": "p0+sealed (quick_stop_veto)",
            "net": float(p0["net"]),
            "exit_reason": p0.get("exit_reason"),
            "ft_sim_hold_sec": int(sim["hold_sec"]),
            "ft_sim_net": float(ft_row["net"]),
        }
    return base


def summarize_rule(
    rows: list[dict[str, Any]],
    *,
    rule: Literal["B", "B_prime", "D"] = "B",
    ft_exit: ExitMode = "flow_bailout",
    ft_ext_open_min: float | None = None,
    ctx_by_day: dict[str, DayWashContext] | None = None,
) -> dict[str, Any]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    picks = []
    for day_rows in by_day.values():
        day = day_rows[0]["day"]
        p = rule_pick_for_day(
            day_rows,
            rule=rule,
            ft_exit=ft_exit,
            ft_ext_open_min=ft_ext_open_min,
            ctx=ctx_by_day.get(day) if ctx_by_day else None,
        )
        if p is not None:
            picks.append(p)
    nets = [float(p["net"]) for p in picks]
    ft_paths = sum(
        1 for p in picks if p["path"].startswith("flow_turn") or p["path"] == "reclaim_br+wash_struct"
    )
    veto_days = sum(1 for p in picks if "veto" in p["path"])
    return {
        "rule": rule,
        "ft_exit": ft_exit,
        "n": len(picks),
        "ft_days": ft_paths,
        "veto_days": veto_days,
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1) if nets else 0.0,
        "picks": picks,
    }


def summarize_rule_with_ft_quick_stop_veto(
    rows: list[dict[str, Any]],
    *,
    ctx_by_day: dict[str, DayWashContext],
    quick_stop_max_sec: int = 600,
    ft_exit: ExitMode = "drive_low_struct",
) -> dict[str, Any]:
    """Aggregate B′ with early-ft quick stop-loss oracle → p0 fallback."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    picks: list[dict[str, Any]] = []
    for day_rows in by_day.values():
        day = day_rows[0]["day"]
        p = rule_pick_b_prime_quick_stop_veto(
            day_rows,
            ctx_by_day.get(day),
            ft_exit=ft_exit,
            quick_stop_max_sec=quick_stop_max_sec,
        )
        if p is not None:
            picks.append(p)
    nets = [float(p["net"]) for p in picks]
    veto_days = sum(1 for p in picks if "quick_stop_veto" in p["path"])
    return {
        "rule": "B_prime",
        "ft_exit": ft_exit,
        "quick_stop_max_sec": quick_stop_max_sec,
        "n": len(picks),
        "veto_days": veto_days,
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1) if nets else 0.0,
        "picks": picks,
    }


def summarize_rule_b(
    rows: list[dict[str, Any]],
    *,
    ft_exit: ExitMode = "flow_bailout",
) -> dict[str, Any]:
    """Aggregate Rule B over probe rows (must include required entry×exit combos)."""
    return summarize_rule(rows, rule="B", ft_exit=ft_exit)


def summarize_rules_matrix(
    rows: list[dict[str, Any]],
    *,
    from_date: str,
    to_date: str,
    ctx_by_day: dict[str, DayWashContext] | None = None,
    hedge_params: DistributionHedgeParams | None = None,
) -> list[dict[str, Any]]:
    """H2 / H1 / ALL slices for B, B', D × ft exits; optional B'+distribution hedge."""
    filtered = [r for r in rows if from_date <= r["day"] <= to_date]
    periods = [
        ("ALL", from_date, to_date),
    ]
    lo = dt.date.fromisoformat(from_date)
    hi = dt.date.fromisoformat(to_date)
    mid = dt.date(2026, 1, 1)
    if lo < mid <= hi:
        periods.extend([
            ("H2_holdout", from_date, "2025-11-30"),
            ("H1_2026", "2026-01-01", to_date),
        ])

    specs: list[tuple[str, Literal["B", "B_prime", "D"], ExitMode]] = [
        ("B_dl", "B", "drive_low_struct"),
        ("B_bailout", "B", "flow_bailout"),
        ("Bprime_dl", "B_prime", "drive_low_struct"),
        ("Bprime_bailout", "B_prime", "flow_bailout"),
        ("D_reclaim", "D", "flow_bailout"),
    ]
    p0_ref = summarize_by_entry_exit(filtered).get("p0+sealed", {})

    out: list[dict[str, Any]] = []
    for period_name, p_lo, p_hi in periods:
        slice_rows = [r for r in filtered if p_lo <= r["day"] <= p_hi]
        if not slice_rows:
            continue
        p0_slice = [r for r in slice_rows if r["entry_mode"] == "p0" and r["exit_mode"] == "sealed"]
        p0_net = round(sum(float(r["net"]) for r in p0_slice), 2) if p0_slice else 0.0
        for spec_name, rule, ft_exit in specs:
            s = summarize_rule(slice_rows, rule=rule, ft_exit=ft_exit)
            out.append({
                "period": period_name,
                "spec": spec_name,
                "rule": rule,
                "ft_exit": ft_exit,
                "hedge": None,
                "n": s["n"],
                "ft_days": s["ft_days"],
                "veto_days": s["veto_days"],
                "hedge_days": 0,
                "net_total": s["net_total"],
                "net_mean": s["net_mean"],
                "win_rate": s["win_rate"],
                "p0_sealed_net": p0_net,
            })
        if ctx_by_day is not None:
            slice_days = sorted({r["day"] for r in slice_rows})
            slice_ctx = {d: ctx_by_day[d] for d in slice_days if d in ctx_by_day}
            h = summarize_rule_with_distribution_hedge(
                slice_rows,
                rule="B_prime",
                ft_exit="drive_low_struct",
                ctx_by_day=slice_ctx,
                params=hedge_params,
            )
            bprime = next(
                (r for r in out if r["period"] == period_name and r["spec"] == "Bprime_dl"),
                None,
            )
            bprime_net = bprime["net_total"] if bprime else 0.0
            out.append({
                "period": period_name,
                "spec": "Bprime_dl_hedge",
                "rule": "B_prime",
                "ft_exit": "drive_low_struct",
                "hedge": "distribution_short",
                "n": h["n"],
                "ft_days": h["ft_days"],
                "veto_days": h["veto_days"],
                "hedge_days": h["hedge_days"],
                "net_total": h["net_total"],
                "net_mean": h["net_mean"],
                "win_rate": h["win_rate"],
                "p0_sealed_net": p0_net,
                "delta_vs_bprime_dl": round(h["net_total"] - bprime_net, 2),
            })
    _ = p0_ref
    return out


def format_rules_matrix_md(matrix: list[dict[str, Any]], *, title: str) -> str:
    has_hedge = any(r.get("hedge") == "distribution_short" for r in matrix)
    header = (
        "| period | rule | ft_exit | hedge | n | ft | veto | flip | net | ΔB′ | mean | WR% | p0+sealed |"
        if has_hedge
        else "| period | rule | ft_exit | n | ft_days | veto | net | mean | WR% | p0+sealed |"
    )
    sep = (
        "|--------|------|---------|-------|---|----|------|------|-----|-----|------|-----|-----------|"
        if has_hedge
        else "|--------|------|---------|---|---------|------|-----|------|-----|-----------|"
    )
    lines = [f"# {title}", "", header, sep]
    for r in matrix:
        if has_hedge:
            delta = r.get("delta_vs_bprime_dl", "")
            delta_s = f"{delta:+}" if delta != "" and delta is not None else "—"
            lines.append(
                f"| {r['period']} | {r['spec']} | {r['ft_exit']} | {r.get('hedge') or '—'} | "
                f"{r['n']} | {r['ft_days']} | {r['veto_days']} | {r.get('hedge_days', 0)} | "
                f"{r['net_total']} | {delta_s} | {r['net_mean']} | {r['win_rate']} | "
                f"{r['p0_sealed_net']} |"
            )
        else:
            lines.append(
                f"| {r['period']} | {r['spec']} | {r['ft_exit']} | {r['n']} | {r['ft_days']} | "
                f"{r['veto_days']} | {r['net_total']} | {r['net_mean']} | {r['win_rate']} | "
                f"{r['p0_sealed_net']} |"
            )
    lines.extend([
        "",
        "## Rule definitions",
        "",
        "- **B**: `flow_turn_ts < p0_ts` → flow_turn + exit; else p0 + sealed",
        "- **B'**: B + V10 veto → p0 + sealed if p0 exists; skip ft-only in 1–3 ATR zone",
        "- **D**: early ft → reclaim_br + wash_struct; else p0 + sealed",
    ])
    if has_hedge:
        lines.extend([
            "- **B'+hedge_distribution_short** (counter-design v2): B' long; on P0+10min with "
            f"px < P0 entry and BR < {DIST_HEDGE_BR_MAX}, **exit long** at signal and **flip short** "
            f"(stop `drive_high + {DIST_HEDGE_SHORT_STOP_PTS}`). Not an overlay — long is closed first.",
            "",
        ])
    else:
        lines.append("")
    return "\n".join(lines) + "\n"


def format_bprime_hedge_detail_md(
    summary: dict[str, Any],
    *,
    title: str,
    compare_net: float | None = None,
) -> str:
    """Day-level B' + distribution hedge report."""
    lines = [
        f"# {title}",
        "",
        "Counter-design v2 · B' long with distribution flip leg.",
        "",
        f"- n={summary['n']} · hedge_days={summary['hedge_days']} · "
        f"net_total={summary['net_total']} · mean={summary['net_mean']} · WR={summary['win_rate']}%",
    ]
    if compare_net is not None:
        lines.append(f"- Δ vs B′ alone: {summary['net_total'] - compare_net:+.2f}")
    lines.extend([
        "",
        "| day | path | hedge | long | short | net | dist_br |",
        "|-----|------|-------|------|-------|-----|---------|",
    ])
    for p in summary["picks"]:
        lines.append(
            f"| {p['day']} | {p['path']} | {p.get('hedge', '—')} | {p.get('long_net', p['net'])} | "
            f"{p.get('short_net', 0)} | {p['net']} | {p.get('dist_br', '—')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def rule_b_net_for_day(
    day_rows: list[dict[str, Any]],
    *,
    ft_exit: ExitMode = "flow_bailout",
) -> dict[str, Any] | None:
    """Rule B: early ``flow_turn`` → ``ft_exit``; else ``p0`` + ``sealed``."""
    return rule_pick_for_day(day_rows, rule="B", ft_exit=ft_exit)


def format_rule_b_md(
    summaries: list[tuple[str, dict[str, Any]]],
    *,
    compare: dict[str, dict[str, float]] | None = None,
) -> str:
    lines = [
        "# GUDT Rule B — flow bailout backtest",
        "",
        "Rule: `flow_turn_ts < p0_ts` → flow_turn + ft_exit; else p0 + sealed.",
        "",
        "| period | n | ft_days | net_total | net_mean |",
        "|--------|---|---------|-----------|----------|",
    ]
    for label, s in summaries:
        lines.append(
            f"| {label} | {s['n']} | {s['ft_days']} | {s['net_total']} | {s['net_mean']} |"
        )
    if compare:
        lines.extend(["", "## Entry×exit reference", ""])
        for key, v in sorted(compare.items()):
            lines.append(f"- `{key}`: n={v['n']} net_total={v['net_total']}")
    lines.append("")
    return "\n".join(lines)


def summarize_by_entry_exit(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Net mean/total grouped by entry×exit."""
    buckets: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        key = (r["entry_mode"], r["exit_mode"])
        buckets.setdefault(key, []).append(float(r["net"]))
    out: dict[str, dict[str, float]] = {}
    for (em, ex), nets in sorted(buckets.items()):
        out[f"{em}+{ex}"] = {
            "n": len(nets),
            "net_total": round(sum(nets), 2),
            "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        }
    return out
