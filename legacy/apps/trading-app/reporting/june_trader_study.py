"""June trader study helpers: regime map, score locked blind candidates.

STATUS: Research exploration only — not Pilot / expectancy / UAT.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Literal

from reporting.osf_liquidity import compute_gap_cohort, compute_liquidity_levels
from reporting.post_trigger_windows import (
    FRICTION_POINTS_DEFAULT,
    WINDOW_MINUTES,
    enrich_post_trigger_windows,
)
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import iter_kbars_in_range
from storage.session_bar_cache import DAY_ANCHOR, DAY_END, NIGHT_ANCHOR, discover_session_close_days

Side = Literal["long", "short"]
StoryId = str

FRICTION_BUFFER_PRIMARY = 8.0  # median path edge @60m must clear this to be primary
STOP_HIT_30_KILL = 0.35


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _day_session_rows(rows: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        ts = r["m15"]["ts"]
        if not ts.startswith(day):
            continue
        t = ts[11:16]
        if "08:45" <= t <= "13:45":
            out.append(r)
    return out


def _night_rows(rows: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    """Evening of ``day`` 15:00 through next calendar dawn (ts on day night or next early)."""
    nxt = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    out = []
    for r in rows:
        ts = r["m15"]["ts"]
        d, t = ts[:10], ts[11:16]
        if d == day and t >= "15:00":
            out.append(r)
        elif d == nxt and t <= "05:00":
            out.append(r)
    return out


def classify_regime(
    *,
    day_net: float,
    day_range: float,
    gap_cohort: str,
    pvm_open: dict[str, str | None],
    recovered_frac: float | None,
) -> str:
    h4_up = pvm_open.get("h4_ma20") == "above" and pvm_open.get("h4_ma60") == "above"
    h1_up = pvm_open.get("h1_ma20") == "above"
    h4_dn = pvm_open.get("h4_ma20") == "below"
    if day_range > 0 and day_range < 450 and h4_up:
        if abs(day_net) < 120:
            return "premium_chop"
    if gap_cohort == "gap_down" and h4_up and recovered_frac is not None and recovered_frac > 0.5:
        return "flush_long"
    if gap_cohort == "gap_up" and h4_dn and recovered_frac is not None and recovered_frac > 0.5:
        return "flush_short"
    if day_net >= 350 and h4_up:
        return "trend_up"
    if day_net <= -350 and (h4_dn or not h4_up):
        return "trend_down"
    if h1_up != h4_up:
        return "transition"
    if h4_up and day_net > 0:
        return "trend_up"
    if not h4_up and day_net < 0:
        return "trend_down"
    return "transition"


def build_regime_map(
    timeline: dict[str, Any],
    *,
    code: str,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
) -> list[dict[str, Any]]:
    rows = timeline["rows"]
    days = sorted({r["m15"]["ts"][:10] for r in rows if "08:45" <= r["m15"]["ts"][11:16] <= "13:45"})
    out: list[dict[str, Any]] = []
    for day_s in days:
        day = datetime.date.fromisoformat(day_s)
        sess = _day_session_rows(rows, day_s)
        if not sess:
            continue
        o = float(sess[0]["m15"]["O"])
        c = float(sess[-1]["m15"]["C"])
        hi = max(float(r["m15"]["H"]) for r in sess)
        lo = min(float(r["m15"]["L"]) for r in sess)
        day_range = hi - lo
        day_net = c - o
        pvm = sess[0].get("price_vs_ma") or {}
        # gap from 1m
        as_of = datetime.datetime.combine(day, datetime.time(9, 15))
        bars = iter_kbars_in_range(
            code,
            day - datetime.timedelta(days=5),
            day,
            cache_dir=cache_dir,
        )
        bars = [b for b in bars if b.ts <= as_of]
        gap_cohort, gap_pts, _, _ = compute_gap_cohort(bars, day)
        levels = compute_liquidity_levels(bars, day, or_minutes=30)
        # recovery from session low toward open (for flush)
        recovered = None
        if day_range > 0 and lo < o:
            recovered = (c - lo) / (o - lo) if o > lo else None
        if gap_cohort == "gap_down" and day_range > 0:
            recovered = max(0.0, (c - lo) / day_range)
        regime = classify_regime(
            day_net=day_net,
            day_range=day_range,
            gap_cohort=gap_cohort,
            pvm_open=pvm,
            recovered_frac=recovered,
        )
        night = _night_rows(rows, day_s)
        night_range = 0.0
        if night:
            night_range = max(float(r["m15"]["H"]) for r in night) - min(
                float(r["m15"]["L"]) for r in night
            )
            if night_range >= 0.5 * max(day_range, 1.0):
                regime = "night_drive" if abs(day_net) < 200 else regime
        out.append(
            {
                "day": day_s,
                "regime": regime,
                "gap_cohort": gap_cohort,
                "gap_points": round(gap_pts, 1),
                "open": o,
                "high": hi,
                "low": lo,
                "close": c,
                "day_range": round(day_range, 1),
                "day_net": round(day_net, 1),
                "or_low": levels.or_range.low if levels.or_range.valid else None,
                "or_high": levels.or_range.high if levels.or_range.valid else None,
                "dawn_low": levels.dawn_low,
                "overnight_low": levels.overnight_low,
                "pvm_open": pvm,
                "night_range": round(night_range, 1),
            }
        )
    return out


def score_candidate(
    cand: dict[str, Any],
    *,
    code: str,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    atr: float = 40.0,
) -> dict[str, Any]:
    """Attach MAE/MFE path scores; does not mutate blind identity fields."""
    entry_ts = datetime.datetime.fromisoformat(cand["entry_ts"])
    entry_price = float(cand["entry_ref"])
    side: Side = cand["side"]
    stop_ref = float(cand["stop_ref"]) if cand.get("stop_ref") is not None else None
    # Night entries sit in 05:00–08:45 dead zone; use longer wall-clock horizons.
    story = str(cand.get("story_id", ""))
    night = story.startswith("N")
    win_mins = (60, 120, 180, 360) if night else WINDOW_MINUTES
    horizon_min = max(win_mins) + 30
    end = entry_ts + datetime.timedelta(minutes=horizon_min)
    bars = iter_kbars_in_range(
        code, entry_ts.date() - datetime.timedelta(days=1), end.date(), cache_dir=cache_dir
    )
    after = [b for b in bars if b.ts > entry_ts]
    windows = enrich_post_trigger_windows(
        entry_price=entry_price,
        entry_ts=int(entry_ts.timestamp()),
        bars_1m_after=after,
        atr=atr,
        side=side,
        stop_ref=stop_ref,
        window_minutes=win_mins,
    )
    # Day stories use 30/60m; night uses 120/180m as first meaningful path checks.
    # (Assign full tuples — do not unpack a 2-tuple into two string names.)
    near_keys = ("mfe_120m", "mae_120m") if night else ("mfe_30m", "mae_30m")
    far_keys = ("mfe_180m", "mae_180m") if night else ("mfe_60m", "mae_60m")
    path_ok_near = False
    if near_keys[0] in windows and near_keys[1] in windows:
        path_ok_near = windows[near_keys[0]] >= windows[near_keys[1]]
    path_ok_far = False
    if far_keys[0] in windows and far_keys[1] in windows:
        path_ok_far = windows[far_keys[0]] >= windows[far_keys[1]]
    early_mfe = windows.get("mfe_15m") or windows.get("mfe_60m")
    early_mae = windows.get("mae_15m") or windows.get("mae_60m")
    story_broke = bool(
        early_mfe is not None
        and early_mae is not None
        and early_mae > early_mfe * 1.5
        and early_mae >= 30
    )
    # Unified edge key for aggregates (day: 60m, night: 180m)
    if night and "mfe_180m" in windows and "mae_180m" in windows:
        windows["path_edge_60m"] = round(windows["mfe_180m"] - windows["mae_180m"], 2)
        windows["path_edge_60m_net_friction5"] = round(
            windows["path_edge_60m"] - FRICTION_POINTS_DEFAULT, 2
        )
    scored = dict(cand)
    scored["windows"] = windows
    scored["path_ok_30m"] = path_ok_near
    scored["path_ok_60m"] = path_ok_far
    scored["story_broke"] = story_broke
    scored["path_supports_narrative"] = path_ok_near and path_ok_far and not story_broke
    scored["night_path"] = night
    return scored


def aggregate_stories(scored: list[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, list[dict[str, Any]]] = {}
    for c in scored:
        key = f"{c['story_id']}|{c['side']}"
        by.setdefault(key, []).append(c)
    summary: dict[str, Any] = {}
    for key, items in by.items():
        n = len(items)
        edges = [
            i["windows"]["path_edge_60m"]
            for i in items
            if "path_edge_60m" in i.get("windows", {})
        ]
        mfe60 = [i["windows"]["mfe_60m"] for i in items if "mfe_60m" in i.get("windows", {})]
        mae60 = [i["windows"]["mae_60m"] for i in items if "mae_60m" in i.get("windows", {})]
        stop30 = [i["windows"].get("stop_hit_30m") for i in items if "stop_hit_30m" in i.get("windows", {})]
        path_ok = sum(1 for i in items if i.get("path_supports_narrative"))
        med_edge = statistics.median(edges) if edges else None
        med_mfe = statistics.median(mfe60) if mfe60 else None
        med_mae = statistics.median(mae60) if mae60 else None
        stop30_rate = (sum(1 for x in stop30 if x) / len(stop30)) if stop30 else None
        kills: list[str] = []
        if n < 5:
            kills.append("n_lt_5_research_only")
        if med_edge is not None and med_edge < FRICTION_BUFFER_PRIMARY:
            kills.append("median_path_edge_60m_lt_friction_buffer_8")
        if stop30_rate is not None and stop30_rate > STOP_HIT_30_KILL:
            kills.append("stop_hit_30m_gt_35pct")
        if med_mfe is not None and med_mae is not None and med_mfe <= 0 and (stop30_rate or 0) > 0.5:
            kills.append("weak_mfe_and_stops")
        if med_edge is None:
            kills.append("no_path_windows")
        primary_eligible = n >= 5 and not any(
            k in kills
            for k in (
                "median_path_edge_60m_lt_friction_buffer_8",
                "stop_hit_30m_gt_35pct",
                "no_path_windows",
                "weak_mfe_and_stops",
            )
        )
        summary[key] = {
            "n": n,
            "path_support_rate": round(path_ok / n, 3) if n else 0,
            "median_mfe_60m": med_mfe,
            "median_mae_60m": med_mae,
            "median_path_edge_60m": med_edge,
            "median_path_edge_60m_net_f5": (
                round(med_edge - FRICTION_POINTS_DEFAULT, 2) if med_edge is not None else None
            ),
            "stop_hit_30m_rate": round(stop30_rate, 3) if stop30_rate is not None else None,
            "kills": kills,
            "primary_eligible": primary_eligible and n >= 5,
        }
    return summary
