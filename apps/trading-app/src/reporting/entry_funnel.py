"""FT-003 Phase 3.6 §C: entry funnel diagnosis (armed forward, pullback replay)."""

from __future__ import annotations

import bisect
import datetime as dt
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from reporting.forward_pnl import TickSeries, _direction_sign, load_tick_series
from reporting.near_miss_aggregate import aggregate_near_miss
from reporting.structure_calibration import ArmedCandidate, parse_momentum_armed
from reporting.uat_report import Episode, compute_episodes, parse_decision_audits
from reporting.volatility_baseline import percentile, threshold_percentile, threshold_pct_gte
from storage.tick_loader import ReplayTick, iter_replay_ticks, resolve_cli_tick_cache_dates
from trading_engine.indicators import IndicatorState

FORWARD_WINDOWS_SEC = (30, 60, 180, 300)
SCHEMA_VERSION = 1

TREND_NOTE = (
    "armed 後順勢位移 ≠ 策略 net edge（設計為等回踩，不追價）。"
    "見 ENTRY_FUNNEL_METRICS §1.3。"
)
REPLAY_NOTE = "回踩漏斗以 `IndicatorState` tick 回放（與 engine VWAP/vol_1s 語意一致）。"
NEAR_MISS_NOTE = (
    "`blocked_*` / `momentum_*` 對 daily_summaries **sum**；"
    "`closest_vwap_distance` 取 **min**。"
)


@dataclass(frozen=True)
class EntryFunnelConfig:
    entry_band_points: float
    momentum_vol_1s: float
    exhaustion_vol: float
    momentum_timeout_sec: int
    vwap_window_min: int = 5


@dataclass
class EpisodeReplayStats:
    ever_near_vwap: bool = False
    ever_vol_dried: bool = False
    both_same_tick: bool = False
    time_to_first_band: int | None = None
    time_to_entry: int | None = None
    pullback_depth: float = 0.0
    closest_vwap_distance: float | None = None
    vol_at_arm: int = 0
    vol_at_entry: int | None = None
    vwap_distance_at_entry: float | None = None
    hit_entry_band: bool = False


def load_entry_funnel_config(config_path: Path) -> EntryFunnelConfig:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    strategy = data.get("strategy") or {}
    return EntryFunnelConfig(
        entry_band_points=float(strategy.get("entry_band_points", 2.0)),
        momentum_vol_1s=float(strategy.get("momentum_vol_1s", 150)),
        exhaustion_vol=float(strategy.get("exhaustion_vol", 15)),
        momentum_timeout_sec=int(strategy.get("momentum_timeout_sec", 180)),
        vwap_window_min=int(strategy.get("vwap_window_min", 5)),
    )


def classify_episode_outcome(ep: Episode) -> str:
    """Outcome cohort per ENTRY_FUNNEL_METRICS §4.5 (entered > veto > risk_blocked > timeout)."""
    if _entry_signal_ts(ep) is not None:
        return "entered"
    for ev in ep.events or []:
        et = ev.get("event_type") or ""
        if et == "structure_veto":
            return "structure_veto"
        if et == "trend_veto":
            return "trend_veto"
    for ev in ep.events or []:
        if (ev.get("event_type") or "") == "risk_blocked":
            return "risk_blocked"
    if ep.outcome == "timeout" or _timeout_ts(ep) is not None:
        return "timeout"
    if ep.outcome == "pending_timeout":
        return "pending_timeout"
    if ep.outcome == "veto":
        return "trend_veto"
    return ep.outcome or "unknown"


def _episode_has_armed(ep: Episode) -> bool:
    return any((ev.get("event_type") or "") == "momentum_armed" for ev in (ep.events or []))


def _armed_ts(ep: Episode) -> int | None:
    if ep.armed_ts is not None:
        return int(ep.armed_ts)
    for ev in ep.events or []:
        if ev.get("event_type") == "momentum_armed":
            return int(ev.get("ts") or 0)
    return None


def _entry_signal_ts(ep: Episode) -> int | None:
    for ev in ep.events or []:
        if ev.get("source") == "signal" and ev.get("event_type") == "entry":
            return int(ev.get("ts") or 0)
    return None


def _timeout_ts(ep: Episode) -> int | None:
    for ev in ep.events or []:
        if ev.get("event_type") == "momentum_timeout":
            return int(ev.get("ts") or 0)
    return None


_TERMINATION_EVENT_TYPES = frozenset(
    {"momentum_timeout", "trend_veto", "structure_veto", "risk_blocked"}
)


def _termination_ts(ep: Episode) -> int | None:
    """Earliest terminal DECISION event (timeout, veto, risk_blocked)."""
    times: list[int] = []
    for ev in ep.events or []:
        if (ev.get("event_type") or "") in _TERMINATION_EVENT_TYPES:
            times.append(int(ev.get("ts") or 0))
    return min(times) if times else None


def _filter_daily_summaries_by_date(
    daily_summaries: list[dict[str, Any]],
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    return [
        day
        for day in daily_summaries
        if (d := day.get("date") or "") and from_date <= d <= to_date
    ]


def episode_end_ts(ep: Episode, cfg: EntryFunnelConfig) -> tuple[int, int, int | None]:
    """Return (armed_ts, end_ts inclusive upper bound, entry_ts)."""
    armed = _armed_ts(ep)
    if armed is None:
        raise ValueError(f"episode {ep.episode_id} missing armed_ts")
    end = armed + cfg.momentum_timeout_sec
    entry_ts = _entry_signal_ts(ep)
    term_ts = _termination_ts(ep)
    if entry_ts is not None:
        end = min(end, entry_ts)
    if term_ts is not None:
        end = min(end, term_ts)
    return armed, end, entry_ts


def _tick_rows_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
) -> list[tuple[int, float, int, int]]:
    rows: list[tuple[int, float, int, int]] = []
    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        rows.append(_tick_to_row(tick))
    return rows


def _tick_to_row(tick: ReplayTick) -> tuple[int, float, int, int]:
    return (
        int(tick.datetime.timestamp()),
        float(tick.close),
        int(tick.volume),
        int(tick.tick_type),
    )


def replay_episode_funnel(
    ticks: list[tuple[int, float, int, int]],
    *,
    armed_ts: int,
    end_ts: int,
    trigger_price: float,
    direction: str,
    cfg: EntryFunnelConfig,
    vol_at_arm_audit: int,
    entry_ts: int | None,
) -> EpisodeReplayStats:
    """Replay ticks with IndicatorState; accumulate pullback funnel flags."""
    ind = IndicatorState(vwap_window_min=cfg.vwap_window_min)
    stats = EpisodeReplayStats(vol_at_arm=vol_at_arm_audit)
    is_long = direction == "Long"

    for ts, price, volume, tick_type in ticks:
        if ts > end_ts:
            break
        ind.update_vwap(ts, price, volume)
        ind.update_momentum(ts, volume, tick_type)

        if ts < armed_ts:
            continue

        vwap = ind.current_vwap
        vol_1s = ind.vol_1s
        dist = abs(price - vwap)
        near_vwap = dist <= cfg.entry_band_points
        vol_dried = vol_1s <= cfg.exhaustion_vol

        if stats.closest_vwap_distance is None or dist < stats.closest_vwap_distance:
            stats.closest_vwap_distance = round(dist, 2)

        if near_vwap:
            stats.ever_near_vwap = True
            if stats.time_to_first_band is None:
                stats.time_to_first_band = ts - armed_ts
            stats.hit_entry_band = True

        if vol_dried:
            stats.ever_vol_dried = True

        if near_vwap and vol_dried:
            stats.both_same_tick = True

        if is_long:
            stats.pullback_depth = max(stats.pullback_depth, max(0.0, trigger_price - price))
        else:
            stats.pullback_depth = max(stats.pullback_depth, max(0.0, price - trigger_price))

        if entry_ts is not None and ts == entry_ts:
            stats.vol_at_entry = vol_1s
            stats.vwap_distance_at_entry = round(dist, 2)

    if entry_ts is not None and stats.time_to_entry is None:
        stats.time_to_entry = entry_ts - armed_ts

    return stats


def armed_forward_window_stats(
    armed: ArmedCandidate,
    series: TickSeries,
    window_sec: int,
    *,
    atr: float | None,
) -> dict[str, float | bool]:
    if not series.timestamps:
        return {
            "MFE_delta": 0.0,
            "MAE_delta": 0.0,
            "close_delta": 0.0,
            "signed_return_over_atr": 0.0,
        }

    sign = _direction_sign(armed.direction)
    start_idx = bisect.bisect_left(series.timestamps, armed.ts)
    if start_idx >= len(series.timestamps):
        start_idx = len(series.timestamps) - 1

    target_ts = armed.ts + window_sec
    end_idx = bisect.bisect_right(series.timestamps, target_ts) - 1
    end_idx = max(start_idx, min(len(series.timestamps) - 1, end_idx))

    trigger = armed.price
    mfe = float("-inf")
    mae = float("-inf")
    for i in range(start_idx, end_idx + 1):
        delta = sign * (series.closes[i] - trigger)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)

    close_delta = sign * (series.closes[end_idx] - trigger)
    atr_denom = atr if atr and atr > 0 else None
    return {
        "MFE_delta": round(mfe if mfe != float("-inf") else 0.0, 2),
        "MAE_delta": round(mae if mae != float("-inf") else 0.0, 2),
        "close_delta": round(close_delta, 2),
        "signed_return_over_atr": round(close_delta / atr_denom, 4) if atr_denom else 0.0,
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def _collect_vol_1s_samples(
    code: str,
    dates: list[dt.date],
    *,
    cache_dir: Path,
) -> list[float]:
    """Per-second aggregated volume samples (same semantics as volatility baseline)."""
    from collections import defaultdict

    samples: list[float] = []
    for day in dates:
        by_second: dict[dt.datetime, float] = defaultdict(float)
        for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
            sec = tick.datetime.replace(microsecond=0)
            by_second[sec] += float(tick.volume)
        for v in by_second.values():
            if v > 0:
                samples.append(v)
    return samples


def _summarize_cohort_forward(
    rows: list[dict[str, Any]],
    windows: tuple[int, ...],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for w in windows:
        key = f"W{w}"
        closes = [float(r["forward"].get(key, {}).get("close_delta", 0)) for r in rows]
        mfes = [float(r["forward"].get(key, {}).get("MFE_delta", 0)) for r in rows]
        maes = [float(r["forward"].get(key, {}).get("MAE_delta", 0)) for r in rows]
        out[key] = {
            "count": len(rows),
            "close_delta_median": _median(closes),
            "MFE_median": _median(mfes),
            "MAE_median": _median(maes),
        }
    return out


def build_entry_funnel_payload(
    *,
    agent: str,
    log_lines: list[str],
    report: dict[str, Any],
    cfg: EntryFunnelConfig,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
    )
    if not dates:
        raise ValueError(f"no tick cache dates for {from_date}..{to_date}")

    episodes = [ep for ep in compute_episodes(log_lines) if _episode_has_armed(ep)]
    decisions = parse_decision_audits(log_lines)
    armed_list = parse_momentum_armed(decisions)
    armed_by_episode = {a.episode_id: a for a in armed_list}

    audit_vol: dict[str, int] = {}
    audit_buy_ratio: dict[str, float] = {}
    for d in decisions:
        if d.event_type == "momentum_armed" and d.episode_id:
            audit_vol[str(d.episode_id)] = int(d.vol_1s or 0)
            audit_buy_ratio[str(d.episode_id)] = float(d.buy_ratio or 0.0)

    tick_series = load_tick_series(code, dates, cache_dir=cache_dir)
    day_ticks: dict[dt.date, list[tuple[int, float, int, int]]] = {}
    for day in dates:
        day_ticks[day] = _tick_rows_for_day(code, day, cache_dir=cache_dir)

    episode_rows: list[dict[str, Any]] = []
    for ep in episodes:
        armed_c = armed_by_episode.get(ep.episode_id)
        if armed_c is None:
            continue
        armed_ts, end_ts, entry_ts = episode_end_ts(ep, cfg)
        day = dt.datetime.fromtimestamp(armed_ts).date()
        ticks = day_ticks.get(day, [])
        if not ticks:
            continue

        replay = replay_episode_funnel(
            ticks,
            armed_ts=armed_ts,
            end_ts=end_ts,
            trigger_price=armed_c.price,
            direction=armed_c.direction,
            cfg=cfg,
            vol_at_arm_audit=audit_vol.get(ep.episode_id, 0),
            entry_ts=entry_ts,
        )
        if entry_ts is not None and replay.time_to_entry is None:
            replay.time_to_entry = entry_ts - armed_ts

        atr = armed_c.atr if armed_c.atr > 0 else None
        forward: dict[str, Any] = {}
        for w in FORWARD_WINDOWS_SEC:
            forward[f"W{w}"] = armed_forward_window_stats(armed_c, tick_series, w, atr=atr)

        outcome = classify_episode_outcome(ep)
        episode_rows.append(
            {
                "episode_id": ep.episode_id,
                "outcome": outcome,
                "direction": armed_c.direction,
                "armed_ts": armed_ts,
                "atr": atr,
                "replay": replay,
                "forward": forward,
                "vol_1s_at_arm": audit_vol.get(ep.episode_id),
                "buy_ratio_at_arm": audit_buy_ratio.get(ep.episode_id),
            }
        )

    armed_n = len(episode_rows)
    vol_samples = _collect_vol_1s_samples(code, dates, cache_dir=cache_dir)
    threshold = cfg.momentum_vol_1s

    vol_at_arm_samples = [
        float(r["vol_1s_at_arm"]) for r in episode_rows if r.get("vol_1s_at_arm") is not None
    ]
    buy_ratio_samples = [
        float(r["buy_ratio_at_arm"]) for r in episode_rows if r.get("buy_ratio_at_arm") is not None
    ]

    funnel_counts = {
        "armed": armed_n,
        "ever_near_vwap": sum(1 for r in episode_rows if r["replay"].ever_near_vwap),
        "ever_vol_dried": sum(1 for r in episode_rows if r["replay"].ever_vol_dried),
        "both_same_tick": sum(1 for r in episode_rows if r["replay"].both_same_tick),
        "entered": sum(1 for r in episode_rows if r["outcome"] == "entered"),
        "timeout": sum(1 for r in episode_rows if r["outcome"] == "timeout"),
    }

    def _pct(num: int, den: int) -> float | None:
        if den <= 0:
            return None
        return round(100.0 * num / den, 1)

    funnel_rates = {
        k: _pct(v, armed_n) if k != "armed" else 100.0
        for k, v in funnel_counts.items()
    }

    by_outcome: dict[str, list[dict[str, Any]]] = {}
    for row in episode_rows:
        by_outcome.setdefault(row["outcome"], []).append(row)

    armed_forward_by_outcome = {
        outcome: _summarize_cohort_forward(rows, FORWARD_WINDOWS_SEC)
        for outcome, rows in sorted(by_outcome.items())
    }

    timeout_eps = [r for r in episode_rows if r["outcome"] == "timeout"]
    timeout_before_band = sum(1 for r in timeout_eps if not r["replay"].ever_near_vwap)
    timeout_after_band_no_vol = sum(
        1
        for r in timeout_eps
        if r["replay"].ever_near_vwap and not r["replay"].ever_vol_dried
    )

    ttb = [
        r["replay"].time_to_first_band
        for r in episode_rows
        if r["replay"].time_to_first_band is not None
    ]
    tte = [
        r["replay"].time_to_entry
        for r in episode_rows
        if r["replay"].time_to_entry is not None
    ]
    pbd = [r["replay"].pullback_depth for r in episode_rows if r["replay"].pullback_depth > 0]
    pbd_over_atr = [
        r["replay"].pullback_depth / float(r["atr"])
        for r in episode_rows
        if (r.get("atr") or 0) > 0 and r["replay"].pullback_depth > 0
    ]

    daily = _filter_daily_summaries_by_date(
        report.get("daily_summaries") or [],
        from_date,
        to_date,
    )
    near_miss_month = aggregate_near_miss(daily) or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "agent": agent,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "config": {
            "entry_band_points": cfg.entry_band_points,
            "momentum_vol_1s": cfg.momentum_vol_1s,
            "exhaustion_vol": cfg.exhaustion_vol,
            "momentum_timeout_sec": cfg.momentum_timeout_sec,
            "vwap_window_min": cfg.vwap_window_min,
        },
        "forward_policy": {
            "windows_sec": list(FORWARD_WINDOWS_SEC),
            "replay_engine": "IndicatorState",
        },
        "vol_threshold_coverage": {
            "pct_vol_gte_threshold": threshold_pct_gte(threshold, vol_samples),
            "pct_vol_lte_exhaustion": threshold_percentile(cfg.exhaustion_vol, vol_samples),
            "vol_1s_at_arm_p50": _median(vol_at_arm_samples),
            "vol_1s_at_arm_p90": (
                round(percentile(sorted(vol_at_arm_samples), 0.9), 1)
                if vol_at_arm_samples
                else None
            ),
            "buy_ratio_at_arm_p50": _median(buy_ratio_samples),
        },
        "pullback_funnel": {
            "counts": funnel_counts,
            "rates_pct_of_armed": funnel_rates,
        },
        "armed_forward_by_outcome": armed_forward_by_outcome,
        "timeout_diagnostics": {
            "timeout_rate": _pct(funnel_counts["timeout"], armed_n),
            "timeout_before_ever_band_pct": _pct(timeout_before_band, len(timeout_eps))
            if timeout_eps
            else None,
            "timeout_after_band_no_vol_pct": _pct(timeout_after_band_no_vol, len(timeout_eps))
            if timeout_eps
            else None,
            "time_to_first_band_p50": _median([float(x) for x in ttb]),
            "time_to_entry_p50": _median([float(x) for x in tte]),
            "pullback_depth_p50": _median(pbd),
            "pullback_depth_over_atr_p50": _median(pbd_over_atr),
        },
        "near_miss_month_aggregate": near_miss_month,
        "episode_count": armed_n,
    }


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) < 1000 else f"{v:.1f}"
    return str(v)


def render_entry_section(
    agent: str,
    log_path: Path,
    payload: dict[str, Any],
) -> str:
    cfg = payload["config"]
    vol = payload.get("vol_threshold_coverage") or {}
    funnel = payload.get("pullback_funnel") or {}
    counts = funnel.get("counts") or {}
    rates = funnel.get("rates_pct_of_armed") or {}
    timeout = payload.get("timeout_diagnostics") or {}
    forward = payload.get("armed_forward_by_outcome") or {}
    nm = payload.get("near_miss_month_aggregate") or {}

    lines = [
        f"**Agent / log / 區間**：`{agent}` / `{log_path.as_posix()}` / "
        f"{payload['from_date']}～{payload['to_date']}",
        "",
        "### C.1 vol_1s 門檻分位",
        "",
        "| 指標 | 值 | 備註 |",
        "|------|-----|------|",
        f"| P(vol_1s ≥ threshold) | {vol.get('pct_vol_gte_threshold', '—')}% | threshold={cfg['momentum_vol_1s']} |",
        f"| P(vol_1s ≤ exhaustion_vol) | {vol.get('pct_vol_lte_exhaustion', '—')}% | exhaustion={cfg['exhaustion_vol']} |",
        f"| vol_1s_at_arm p50 / p90 | {vol.get('vol_1s_at_arm_p50', '—')} / {vol.get('vol_1s_at_arm_p90', '—')} | armed cohort |",
        "",
        "### C.2 armed 順勢窗口（固定 Δt：30 / 60 / 180 秒）",
        "",
        f"> {TREND_NOTE}",
        "",
        "| Outcome | N | W30 close_delta med | W60 | W180 | MFE_180 med | MAE_180 med |",
        "|---------|---|---------------------|-----|------|-------------|-------------|",
    ]

    for outcome in ("entered", "timeout", "trend_veto", "structure_veto", "risk_blocked", "pending_timeout", "unknown"):
        if outcome not in forward:
            continue
        block = forward[outcome]
        w30 = block.get("W30") or {}
        w60 = block.get("W60") or {}
        w180 = block.get("W180") or {}
        lines.append(
            f"| {outcome} | {w30.get('count', 0)} | "
            f"{_fmt(w30.get('close_delta_median'))} | "
            f"{_fmt(w60.get('close_delta_median'))} | "
            f"{_fmt(w180.get('close_delta_median'))} | "
            f"{_fmt(w180.get('MFE_median'))} | "
            f"{_fmt(w180.get('MAE_median'))} |"
        )

    lines.extend(
        [
            "",
            "### C.3 回踩漏斗轉化率",
            "",
            f"> {REPLAY_NOTE}",
            "",
            "| 階段 | count | % of armed |",
            "|------|-------|------------|",
        ]
    )
    for stage in ("armed", "ever_near_vwap", "ever_vol_dried", "both_same_tick", "entered", "timeout"):
        lines.append(
            f"| {stage} | {counts.get(stage, '—')} | {rates.get(stage, '—')}% |"
        )

    lines.extend(
        [
            "",
            "### C.4 timeout 與 time_to_first_band",
            "",
            "| 指標 | 值 |",
            "|------|-----|",
            f"| timeout_rate | {timeout.get('timeout_rate', '—')}% |",
            f"| timeout 前從未 near_vwap 占比 | {timeout.get('timeout_before_ever_band_pct', '—')}% |",
            f"| time_to_first_band p50（秒） | {timeout.get('time_to_first_band_p50', '—')} |",
            f"| time_to_entry p50（entered 子集） | {timeout.get('time_to_entry_p50', '—')} |",
            f"| pullback_depth_over_atr p50 | {timeout.get('pullback_depth_over_atr_p50', '—')} |",
            "",
            "### C.5 near_miss（valid 月 **累計**）",
            "",
        ]
    )
    agg_days = nm.get("_aggregated_from_days")
    if agg_days:
        lines.append(f"> {NEAR_MISS_NOTE} 跨 **{agg_days}** 個交易日。")
    lines.extend(["", "| 指標 | 值 |", "|------|-----|"])
    for key in (
        "momentum_episodes",
        "momentum_timeout",
        "blocked_both",
        "blocked_vwap_only",
        "blocked_vol_only",
        "closest_vwap_distance",
    ):
        if key in nm:
            lines.append(f"| {key} | {nm[key]} |")

    return "\n".join(lines) + "\n"


def merge_entry_into_markdown(markdown_path: Path, entry_section: str, *, agent: str) -> None:
    """Append or replace one agent block inside section C."""
    text = markdown_path.read_text(encoding="utf-8")
    marker = "## C. 進場漏斗（P0 — baseline valid log + tick）"
    d_marker = "## D. 出場診斷（P0 — baseline valid）"
    if marker not in text:
        if d_marker not in text:
            raise ValueError(f"{markdown_path}: missing section C and D markers")
        insert = (
            f"\n---\n\n{marker}\n\n"
            "（由 `ft003_episode_diagnosis.py` 填入）\n\n---\n\n"
        )
        text = text.replace(f"\n{d_marker}", insert + d_marker, 1)
        markdown_path.write_text(text, encoding="utf-8")
        text = markdown_path.read_text(encoding="utf-8")
    start = text.index(marker)
    rest = text[start:]
    c_end = rest.find("\n---\n", len(marker))
    if c_end < 0:
        raise ValueError(f"{markdown_path}: cannot find end of section C")
    c_body = rest[len(marker) : c_end].strip()
    agent_hdr = f"**Agent / log / 區間**：`{agent}` /"
    if agent_hdr in c_body:
        a_start = c_body.index(agent_hdr)
        next_agent = c_body.find("\n\n**Agent / log / 區間**：`", a_start + 1)
        if next_agent < 0:
            c_body = c_body[:a_start].rstrip() + "\n\n" + entry_section.strip()
        else:
            c_body = (
                c_body[:a_start].rstrip()
                + "\n\n"
                + entry_section.strip()
                + "\n\n"
                + c_body[next_agent + 2 :].lstrip()
            )
    elif "（由 `ft003_episode_diagnosis.py` 填入）" in c_body or c_body.startswith("**Agent"):
        if "（由 `ft003_episode_diagnosis.py` 填入）" in c_body:
            c_body = entry_section.strip()
        else:
            c_body = c_body.rstrip() + "\n\n" + entry_section.strip()
    else:
        c_body = entry_section.strip()
    new_rest = marker + "\n\n" + c_body + "\n" + rest[c_end:]
    markdown_path.write_text(text[:start] + new_rest, encoding="utf-8")
