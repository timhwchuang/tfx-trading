"""OSF: HTF + 15m sweep/FVG setup + 5m trigger (long-only, bar-based)."""

from __future__ import annotations

import datetime
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.htf_regime_census import HtfMode, evaluate_htf_at, htf_allows
from reporting.osf_liquidity import LiquidityPool, compute_liquidity_levels, deepest_sweep_pool
from reporting.osf_outlook import build_day_outlook, load_store_for_outlook
from reporting.osf_session_context import (
    OsfBarStore,
    OsfDayContext,
    session_day_bars,
)
from reporting.post_trigger_windows import WINDOW_MINUTES, enrich_post_trigger_windows
from reporting.simulate_bar_structure_exit import simulate_bar_structure_exit_long
from reporting.smc_bar_structure import active_bullish_fvg, displacement_before_fvg
from reporting.volatility_baseline import atr_series_from_bars
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import DAY_ANCHOR, DAY_END

SCHEMA_VERSION = 1
FRICTION_POINTS = 5.0
SETUP_START = datetime.time(9, 30)
TRIGGER_END = datetime.time(13, 0)
SWING_LB = 2
MIN_DISP_ATR_K = 1.0
DEFAULT_ATR_PERIOD = 14
DEFAULT_MIN_ATR = 25.0

LiquidityMode = Literal["or_only", "pools", "pools_or"]


@dataclass(frozen=True)
class OsfParams:
    or_minutes: int = 30
    max_fvg_age_15m: int = 8
    retest_min_frac: float = 0.33
    k_sl: float = 1.0
    htf_mode: HtfMode = "h4_only"
    liquidity_mode: LiquidityMode = "pools"
    require_displacement: bool = True

    def key(self) -> str:
        disp = "d1" if self.require_displacement else "d0"
        return (
            f"or{self.or_minutes}_age{self.max_fvg_age_15m}"
            f"_htf{str(self.htf_mode)}_liq{self.liquidity_mode}"
            f"_rf{self.retest_min_frac:g}_ksl{self.k_sl:g}_{disp}"
        )

    @classmethod
    def relaxed(cls, *, htf_mode: HtfMode = "none") -> OsfParams:
        """Looser Phase-0 replay preset (exploration only)."""
        return cls(
            or_minutes=15,
            max_fvg_age_15m=16,
            retest_min_frac=0.2,
            k_sl=1.2,
            htf_mode=htf_mode,
            liquidity_mode="pools_or",
            require_displacement=False,
        )


@dataclass
class OsfSetup:
    setup_ts: datetime.datetime
    sweep_low: float
    fvg_low: float
    fvg_high: float
    sweep_pool: LiquidityPool
    gap_cohort: str


def _atr_at_bar(bars: list[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume))
        for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=DEFAULT_ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def _pool_levels_for_sweep(
    levels,
    mode: LiquidityMode,
) -> list[tuple[LiquidityPool, float]]:
    pools: list[tuple[LiquidityPool, float]] = []
    if mode in ("or_only", "pools_or") and levels.or_range.valid:
        pools.append(("or_low", levels.or_range.low))
    if mode in ("pools", "pools_or"):
        if levels.dawn_low is not None:
            pools.append(("dawn_low", levels.dawn_low))
        if levels.overnight_low is not None:
            pools.append(("overnight_low", levels.overnight_low))
    return pools


def _diagnose_15m_bar(
    bar_15m: KBarRecord,
    pools: list[tuple[LiquidityPool, float]],
    bars_15m: list[KBarRecord],
    *,
    params: OsfParams,
    as_of: datetime.datetime,
) -> str:
    low = float(bar_15m.Low)
    close = float(bar_15m.Close)
    hits = [
        (name, px)
        for name, px in pools
        if low < px and close > px
    ]
    if not hits:
        return "no_sweep"
    if close < float(bar_15m.Open):
        return "bearish_15m_close"
    fvg = active_bullish_fvg(
        bars_15m,
        as_of=as_of,
        max_age_bars=params.max_fvg_age_15m,
        tf_minutes=15,
    )
    if fvg is None:
        return "no_fvg"
    if params.require_displacement:
        atr = _atr_at_bar(bars_15m, len(bars_15m) - 1)
        if not displacement_before_fvg(
            bars_15m, fvg, min_body_atr_k=MIN_DISP_ATR_K, atr=atr
        ):
            return "no_displacement"
    return "setup_ok"


def _detect_15m_setup(
    bar_15m: KBarRecord,
    levels,
    pools: list[tuple[LiquidityPool, float]],
    bars_15m: list[KBarRecord],
    *,
    params: OsfParams,
    as_of: datetime.datetime,
) -> OsfSetup | None:
    low = float(bar_15m.Low)
    close = float(bar_15m.Close)
    hits: list[tuple[LiquidityPool, float]] = []
    sweep_low = low
    for pool_name, pool_px in pools:
        if low < pool_px and close > pool_px:
            hits.append((pool_name, pool_px))
            sweep_low = min(sweep_low, low)
    if not hits:
        return None
    swept_pool = deepest_sweep_pool(hits)
    if close < float(bar_15m.Open):
        return None
    fvg = active_bullish_fvg(
        bars_15m,
        as_of=as_of,
        max_age_bars=params.max_fvg_age_15m,
        tf_minutes=15,
    )
    if fvg is None:
        return None
    atr = _atr_at_bar(bars_15m, len(bars_15m) - 1)
    if params.require_displacement and not displacement_before_fvg(
        bars_15m, fvg, min_body_atr_k=MIN_DISP_ATR_K, atr=atr
    ):
        return None
    return OsfSetup(
        setup_ts=bar_15m.ts,
        sweep_low=sweep_low,
        fvg_low=fvg.fvg_low,
        fvg_high=fvg.fvg_high,
        sweep_pool=swept_pool,
        gap_cohort=levels.gap_cohort,
    )


def session_tf_bars_for_day(
    closed_tf: list[KBarRecord],
    day: datetime.date,
    *,
    start: datetime.time | None = None,
    end: datetime.time | None = None,
) -> list[KBarRecord]:
    """Filter multi-day closed TF series to one calendar day (+ optional time window)."""
    out = [b for b in closed_tf if b.ts.date() == day]
    if start is not None:
        out = [b for b in out if b.ts.time() >= start]
    if end is not None:
        out = [b for b in out if b.ts.time() <= end]
    return out


def _detect_5m_trigger(
    bar_5m: KBarRecord,
    setup: OsfSetup,
    bars_5m: list[KBarRecord],
    *,
    params: OsfParams,
) -> bool:
    if bar_5m.ts <= setup.setup_ts:
        return False
    span = setup.fvg_high - setup.fvg_low
    if span <= 0:
        return False
    thresh = setup.fvg_low + params.retest_min_frac * span
    if float(bar_5m.Low) > setup.fvg_high:
        return False
    if float(bar_5m.Close) < thresh:
        return False
    if float(bar_5m.Close) <= float(bar_5m.Open):
        return False
    for b in bars_5m:
        if setup.setup_ts < b.ts <= bar_5m.ts and float(b.Close) < setup.sweep_low:
            return False
    return True


def scan_day_long(
    code: str,
    day: datetime.date,
    *,
    params: OsfParams,
    store: OsfBarStore,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """Phase-0 long scan: **first complete 15m setup**, then 5m trigger until TRIGGER_END.

    Does not retry later 15m setups if the first setup never triggers (counterfactual
    simplicity; use ``replay_day_long`` reject counts for multi-bar diagnostics).
    Empty day-session 1m (no tape for ``day``) returns zero funnel without OR/HTF noise.
    """
    funnel = {
        "days": 1,
        "or_valid": 0,
        "htf_ok": 0,
        "sweep_15m": 0,
        "fvg_15m": 0,
        "trigger_5m": 0,
        "entry": 0,
    }
    ctx = OsfDayContext.load(code, day, store=store)
    if ctx is None:
        return None, funnel

    as_of_session_end = datetime.datetime.combine(day, DAY_END)
    snap_day = ctx.snapshot(as_of_session_end)
    if not session_day_bars(snap_day.bars_1m, day):
        return None, funnel

    or_end = datetime.datetime.combine(day, DAY_ANCHOR) + datetime.timedelta(
        minutes=params.or_minutes
    )
    snap_or = ctx.snapshot(or_end)
    levels = compute_liquidity_levels(
        snap_or.bars_1m, day, or_minutes=params.or_minutes
    )
    if not levels.or_range.valid:
        return None, funnel
    funnel["or_valid"] = 1

    pools = _pool_levels_for_sweep(levels, params.liquidity_mode)
    setup: OsfSetup | None = None
    entry_row: dict[str, Any] | None = None

    as_of_htf = datetime.datetime.combine(day, SETUP_START)
    snap_htf = ctx.snapshot(as_of_htf)
    flags = evaluate_htf_at(snap_htf, levels=levels)
    if not htf_allows(flags, params.htf_mode):
        return None, funnel
    funnel["htf_ok"] = 1

    # snap_day already taken at DAY_END for empty-session guard.
    snap_session = snap_day
    # Multi-day store keeps full TF history; restrict scan/trigger to this session day.
    bars_15m_all = session_tf_bars_for_day(
        snap_session.closed.get("15m", []), day
    )
    bars_5m_session = session_tf_bars_for_day(
        snap_session.closed.get("5m", []), day
    )
    scan_15m = session_tf_bars_for_day(
        bars_15m_all, day, start=SETUP_START, end=TRIGGER_END
    )

    for bar_15m in scan_15m:
        as_of = bar_15m.ts
        snap = ctx.snapshot(as_of)
        b15 = snap.closed.get("15m", [])
        reason = _diagnose_15m_bar(
            bar_15m, pools, b15, params=params, as_of=as_of
        )
        if reason == "no_sweep":
            continue
        funnel["sweep_15m"] = 1
        if reason in ("bearish_15m_close", "no_fvg"):
            continue
        # FVG present (setup_ok or failed only on displacement).
        funnel["fvg_15m"] = 1
        if reason != "setup_ok":
            continue
        cand = _detect_15m_setup(
            bar_15m,
            levels,
            pools,
            b15,
            params=params,
            as_of=as_of,
        )
        if cand is None:
            continue
        setup = cand
        break

    if setup is None:
        return None, funnel

    bars_5m_trigger = [
        b for b in bars_5m_session if b.ts.time() <= TRIGGER_END
    ]
    for bar_5m in bars_5m_trigger:
        if bar_5m.ts <= setup.setup_ts or bar_5m.ts.time() > TRIGGER_END:
            continue
        snap = ctx.snapshot(bar_5m.ts)
        b5 = snap.closed.get("5m", [])
        if not _detect_5m_trigger(bar_5m, setup, b5, params=params):
            continue
        funnel["trigger_5m"] = 1
        entry_price = float(bar_5m.Close)
        entry_ts = bar_5m.ts
        sess = session_day_bars(snap.bars_1m, day)
        session_high = max((float(b.High) for b in sess), default=entry_price)
        exit_sim = simulate_bar_structure_exit_long(
            entry_price=entry_price,
            entry_ts=entry_ts,
            sweep_low=setup.sweep_low,
            fvg_low=setup.fvg_low,
            session_high=session_high,
            bars_5m=bars_5m_session,
            bars_15m=bars_15m_all,
            k_sl=params.k_sl,
        )
        post_horizon = min(
            entry_ts + datetime.timedelta(minutes=max(WINDOW_MINUTES)),
            as_of_session_end,
        )
        snap_post = ctx.snapshot(post_horizon)
        after_1m = [b for b in snap_post.bars_1m if b.ts > entry_ts]
        windows = enrich_post_trigger_windows(
            entry_price=entry_price,
            entry_ts=int(entry_ts.timestamp()),
            bars_1m_after=after_1m,
            atr=_atr_at_bar(b5, len(b5) - 1),
        )
        gross = float(exit_sim["gross_pnl"])
        net = gross - FRICTION_POINTS
        funnel["entry"] = 1
        entry_row = {
            "day": day.isoformat(),
            "param": params.key(),
            "htf_mode": params.htf_mode,
            "liquidity_mode": params.liquidity_mode,
            "gap_cohort": setup.gap_cohort,
            "sweep_pool": setup.sweep_pool,
            "entry_ts": int(entry_ts.timestamp()),
            "entry_price": round(entry_price, 1),
            "setup_ts": int(setup.setup_ts.timestamp()),
            "fvg_low": round(setup.fvg_low, 1),
            "fvg_high": round(setup.fvg_high, 1),
            "sweep_low": round(setup.sweep_low, 1),
            "gross_pnl": gross,
            "net_pnl": round(net, 2),
            "exit": exit_sim,
            "post_trigger": windows,
        }
        break

    return entry_row, funnel


def replay_day_long(
    code: str,
    day: datetime.date,
    *,
    params: OsfParams,
    store: OsfBarStore,
    include_outlook: bool = False,
) -> dict[str, Any]:
    """Single-day funnel replay with per-15m rejection counts."""
    entry_row, funnel = scan_day_long(code, day, params=params, store=store)
    ctx = OsfDayContext.load(code, day, store=store)
    if ctx is None:
        return {
            "day": day.isoformat(),
            "params": params.key(),
            "htf_mode": params.htf_mode,
            "liquidity_mode": params.liquidity_mode,
            "context": None,
            "funnel": funnel,
            "setup_15m_rejects": {},
            "first_setup_bar": None,
            "entry": entry_row,
            "outlook": None,
        }
    or_end = datetime.datetime.combine(day, DAY_ANCHOR) + datetime.timedelta(
        minutes=params.or_minutes
    )
    snap_or = ctx.snapshot(or_end)
    levels = compute_liquidity_levels(
        snap_or.bars_1m, day, or_minutes=params.or_minutes
    )
    pools = _pool_levels_for_sweep(levels, params.liquidity_mode)
    flags = evaluate_htf_at(ctx.snapshot(datetime.datetime.combine(day, SETUP_START)), levels=levels)

    reject_counts: dict[str, int] = {}
    first_setup_bar: dict[str, Any] | None = None
    bars_15m_all = session_tf_bars_for_day(
        ctx.snapshot(datetime.datetime.combine(day, DAY_END)).closed.get("15m", []),
        day,
    )
    scan_15m = session_tf_bars_for_day(
        bars_15m_all, day, start=SETUP_START, end=TRIGGER_END
    )
    for bar_15m in scan_15m:
        snap = ctx.snapshot(bar_15m.ts)
        reason = _diagnose_15m_bar(
            bar_15m,
            pools,
            snap.closed.get("15m", []),
            params=params,
            as_of=bar_15m.ts,
        )
        reject_counts[reason] = reject_counts.get(reason, 0) + 1
        if reason == "setup_ok" and first_setup_bar is None:
            setup = _detect_15m_setup(
                bar_15m,
                levels,
                pools,
                snap.closed.get("15m", []),
                params=params,
                as_of=bar_15m.ts,
            )
            first_setup_bar = {
                "ts": bar_15m.ts.isoformat(),
                "sweep_pool": setup.sweep_pool if setup else None,
                "low": float(bar_15m.Low),
                "close": float(bar_15m.Close),
            }

    return {
        "day": day.isoformat(),
        "params": params.key(),
        "htf_mode": params.htf_mode,
        "liquidity_mode": params.liquidity_mode,
        "context": {
            "gap_cohort": levels.gap_cohort,
            "gap_points": round(levels.gap_points, 1),
            "or_valid": levels.or_range.valid,
            "or_low": levels.or_range.low,
            "or_high": levels.or_range.high,
            "dawn_low": levels.dawn_low,
            "overnight_low": levels.overnight_low,
            "htf_flags": {
                "daily_long": flags.daily_long,
                "h4_bos_long": flags.h4_bos_long,
                "h4_discount": flags.h4_discount,
                "h1_tactical_long": flags.h1_tactical_long,
                "htf_h4_only": flags.htf_h4_only,
            },
        },
        "funnel": funnel,
        "setup_15m_rejects": reject_counts,
        "first_setup_bar": first_setup_bar,
        "entry": entry_row,
        "outlook": build_day_outlook(store, day) if include_outlook else None,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    gross = [float(r["gross_pnl"]) for r in rows]
    net = [float(r["net_pnl"]) for r in rows]
    return {
        "n": len(rows),
        "gross_mean": round(statistics.mean(gross), 2),
        "net_mean": round(statistics.mean(net), 2),
        "gross_median": round(statistics.median(gross), 2),
        "win_rate": round(sum(1 for g in gross if g > 0) / len(gross), 3),
    }


def build_osf_payload(
    code: str,
    days: list[datetime.date],
    *,
    params: OsfParams,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    store: OsfBarStore | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    funnel_totals = {
        "days": 0,
        "or_valid": 0,
        "htf_ok": 0,
        "sweep_15m": 0,
        "fvg_15m": 0,
        "trigger_5m": 0,
        "entry": 0,
    }
    if store is None:
        store = OsfBarStore.load_range(code, days, cache_dir=cache_dir)
    if store is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "code": code,
            "params": params.key(),
            "htf_mode": params.htf_mode,
            "liquidity_mode": params.liquidity_mode,
            "rows": [],
            "funnel": funnel_totals,
            "summary": {"n": 0},
        }
    for day in sorted(days):
        row, funnel = scan_day_long(code, day, params=params, store=store)
        for k in funnel_totals:
            funnel_totals[k] += funnel.get(k, 0)
        if row is not None:
            rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "code": code,
        "params": params.key(),
        "htf_mode": params.htf_mode,
        "liquidity_mode": params.liquidity_mode,
        "rows": rows,
        "funnel": funnel_totals,
        "summary": _summarize(rows),
    }