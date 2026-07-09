"""June path-OK story parameter tune (exploration only).

Contract
--------
- Input: existing month timeline JSON + on-disk 1m kbars (TMFR1).
- Emit candidates from **rules only** (entry_ts, stop_ref), then score via
  ``june_trader_study.score_candidate`` (MAE/MFE). Never score before emit.
- Small fixed grids only (``iter_a_plus_grid`` / ``iter_c_plus_grid`` /
  ``iter_a_minus_grid``). One June pass — no iterative knob spam.
- STATUS: Research exploration. Path support ≠ expectancy / Pilot / Holdout gate.

Does not modify ``june_2026_candidates_blind.json``.
"""

from __future__ import annotations

import bisect
import datetime
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.june_trader_study import (
    FRICTION_BUFFER_PRIMARY,
    STOP_HIT_30_KILL,
    aggregate_stories,
    score_candidate,
)
from reporting.osf_liquidity import compute_liquidity_levels
from reporting.osf_trader_scan import _day_bars_from_disk
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord, iter_kbars_in_range

StopMode = Literal["or_high_minus_30", "or_mid", "or_low"]
ShortStopMode = Literal["or_high_plus_20", "or_mid", "bar_high_plus_20"]
PoolMode = Literal["any", "or_only", "pools_pref"]
H4Mode = Literal["none", "dual_above", "dual_below"]
H1Mode = Literal["none", "not_below"]
# Short stack filter (do not reuse H1Mode "not_below" — inverted meaning).
ShortH1Mode = Literal["none", "require_below"]

# Explicit aggregate key per family (story_id|side) — do not use next(iter(agg)).
_FAMILY_AGG_KEY: dict[str, str] = {
    "A+": "A+|long",
    "C+": "C+|long",
    "A-+": "A-+|short",
}


@dataclass(frozen=True)
class APlusParams:
    h4: H4Mode = "dual_above"
    h1: H1Mode = "none"
    stop: StopMode = "or_mid"
    hold_bars: int = 3  # search window of 5m bars after first OR break (any-of)

    def key(self) -> str:
        return f"A+_h4{self.h4}_h1{self.h1}_stop{self.stop}_hold{self.hold_bars}"


@dataclass(frozen=True)
class CPlusParams:
    h4: H4Mode = "dual_above"
    pool: PoolMode = "any"
    stop_buffer: float = 0.0  # subtract from sweep low for long stop

    def key(self) -> str:
        return f"C+_h4{self.h4}_pool{self.pool}_buf{self.stop_buffer:g}"


@dataclass(frozen=True)
class AMinusParams:
    h4: H4Mode = "dual_below"
    h1: ShortH1Mode = "none"
    stop: ShortStopMode = "or_mid"

    def key(self) -> str:
        return f"A-+_h4{self.h4}_h1{self.h1}_stop{self.stop}"


def _pvm_at_open(day_rows: list[dict[str, Any]]) -> dict[str, Any]:
    day_sess = [
        r
        for r in day_rows
        if "08:45" <= r["m15"]["ts"][11:16] <= "13:45"
    ]
    if not day_sess:
        return {}
    return day_sess[0].get("price_vs_ma") or {}


def _h4_ok(pvm: dict[str, Any], mode: H4Mode) -> bool:
    if mode == "none":
        return True
    a20, a60 = pvm.get("h4_ma20"), pvm.get("h4_ma60")
    if mode == "dual_above":
        return a20 == "above" and a60 == "above"
    if mode == "dual_below":
        return a20 == "below" and a60 == "below"
    return True


def _h1_ok(pvm: dict[str, Any], mode: H1Mode) -> bool:
    if mode == "none":
        return True
    if mode == "not_below":
        # Missing h1_ma20 is pass (unknown ≠ below). Stricter would require key present.
        return pvm.get("h1_ma20") != "below"
    return True


def _stop_long(or_high: float, or_low: float, mode: StopMode) -> float:
    if mode == "or_high_minus_30":
        return or_high - 30.0
    if mode == "or_mid":
        return (or_high + or_low) / 2.0
    return or_low  # or_low


def _stop_short(
    or_high: float,
    or_low: float,
    bar_high: float,
    mode: ShortStopMode,
) -> float:
    if mode == "or_high_plus_20":
        return or_high + 20.0
    if mode == "or_mid":
        return (or_high + or_low) / 2.0
    return max(or_high, bar_high) + 20.0


def scan_a_plus_long(
    day: datetime.date,
    *,
    bars_15m: list[KBarRecord],
    bars_5m: list[KBarRecord],
    or_high: float,
    or_low: float,
    pvm: dict[str, Any],
    params: APlusParams,
    regime_tag: str,
) -> dict[str, Any] | None:
    """OR high break + 5m hold; optional h4/h1 filters.

    Only the **first** 15m close above OR high (09:30–11:00) is considered
    (same contract as ``_scan_or_breakout_hold``). ``hold_bars`` is the 5m
    search window length after that break, not a consecutive-hold count.
    """
    if not _h4_ok(pvm, params.h4) or not _h1_ok(pvm, params.h1):
        return None
    if or_high <= or_low:
        return None
    if params.hold_bars < 1:
        return None
    m5_ts = [b.ts for b in bars_5m]
    for bar in bars_15m:
        t = bar.ts.time()
        if t < datetime.time(9, 30) or t > datetime.time(11, 0):
            continue
        if float(bar.Close) <= or_high:
            continue
        i5 = bisect.bisect_right(m5_ts, bar.ts)
        for b5 in bars_5m[i5 : i5 + params.hold_bars]:
            if float(b5.Low) >= or_high and float(b5.Close) > float(b5.Open):
                stop = _stop_long(or_high, or_low, params.stop)
                return {
                    "id": f"{params.key()}|{day.isoformat()}",
                    "day": day.isoformat(),
                    "side": "long",
                    "story_id": "A+",
                    "entry_ts": b5.ts.isoformat(),
                    "entry_ref": round(float(b5.Close), 1),
                    "stop_ref": round(stop, 1),
                    "regime_tag": regime_tag,
                    "rationale": (
                        f"A+ OR hold h4={params.h4} h1={params.h1} "
                        f"stop={params.stop} or_high={or_high:.0f}"
                    ),
                    "confidence": "B",
                    "source": "tune_a_plus",
                    "variant": params.key(),
                }
        # First break only — do not hunt later 15m breaks (baseline contract).
        return None
    return None


def scan_c_plus_long(
    day: datetime.date,
    *,
    bars_15m: list[KBarRecord],
    bars_5m: list[KBarRecord],
    pools: list[tuple[str, float]],
    pvm: dict[str, Any],
    params: CPlusParams,
    regime_tag: str,
) -> dict[str, Any] | None:
    """Sweep+reclaim + 5m break of sweep high; require h4 dual above."""
    if not _h4_ok(pvm, params.h4):
        return None
    if params.pool == "or_only":
        pools = [(n, px) for n, px in pools if n == "or_low"]
    elif params.pool == "pools_pref":
        pref = [(n, px) for n, px in pools if n in ("overnight_low", "dawn_low")]
        pools = pref or pools
    if not pools:
        return None
    m5_ts = [b.ts for b in bars_5m]
    for bar in bars_15m:
        t = bar.ts.time()
        if t < datetime.time(9, 30) or t > datetime.time(13, 30):
            continue
        low, close, high = float(bar.Low), float(bar.Close), float(bar.High)
        if close < float(bar.Open):
            continue
        hit = [(n, px) for n, px in pools if low < px < close]
        if not hit:
            continue
        pool_name = min(hit, key=lambda x: x[1])[0]
        i5 = bisect.bisect_right(m5_ts, bar.ts)
        for b5 in bars_5m[i5:]:
            if b5.ts.time() > datetime.time(13, 30):
                break
            if float(b5.Close) > high and float(b5.Close) > float(b5.Open):
                stop = low - params.stop_buffer
                return {
                    "id": f"{params.key()}|{day.isoformat()}",
                    "day": day.isoformat(),
                    "side": "long",
                    "story_id": "C+",
                    "entry_ts": b5.ts.isoformat(),
                    "entry_ref": round(float(b5.Close), 1),
                    "stop_ref": round(stop, 1),
                    "regime_tag": regime_tag,
                    "rationale": (
                        f"C+ sweep {pool_name} L{low:.0f} reclaim; "
                        f"5m> {high:.0f}; h4={params.h4}"
                    ),
                    "confidence": "B",
                    "source": "tune_c_plus",
                    "variant": params.key(),
                }
    return None


def scan_a_minus_short(
    day: datetime.date,
    *,
    bars_15m: list[KBarRecord],
    or_high: float,
    or_low: float,
    pvm: dict[str, Any],
    params: AMinusParams,
    regime_tag: str,
) -> dict[str, Any] | None:
    """15m break OR low bearish close; stack filter (h4 dual_below + optional h1 below)."""
    if not _h4_ok(pvm, params.h4):
        return None
    if params.h1 == "require_below" and pvm.get("h1_ma20") != "below":
        return None
    if or_high <= or_low:
        return None
    for bar in bars_15m:
        t = bar.ts.time()
        if t < datetime.time(9, 30) or t > datetime.time(12, 0):
            continue
        if float(bar.Low) < or_low and float(bar.Close) < or_low and float(bar.Close) < float(bar.Open):
            stop = _stop_short(or_high, or_low, float(bar.High), params.stop)
            return {
                "id": f"{params.key()}|{day.isoformat()}",
                "day": day.isoformat(),
                "side": "short",
                "story_id": "A-+",
                "entry_ts": bar.ts.isoformat(),
                "entry_ref": round(float(bar.Close), 1),
                "stop_ref": round(stop, 1),
                "regime_tag": regime_tag,
                "rationale": (
                    f"A-+ OR low break h4={params.h4} h1={params.h1} "
                    f"stop={params.stop} or_low={or_low:.0f}"
                ),
                "confidence": "B",
                "source": "tune_a_minus",
                "variant": params.key(),
            }
    return None


def _day_list_from_timeline(timeline: dict[str, Any]) -> list[str]:
    days = sorted(
        {
            r["m15"]["ts"][:10]
            for r in timeline["rows"]
            if "08:45" <= r["m15"]["ts"][11:16] <= "13:45"
        }
    )
    return days


def _load_day_context(
    code: str,
    day: datetime.date,
    timeline_rows: list[dict[str, Any]],
    *,
    cache_dir: Path,
    regime_by_day: dict[str, str],
) -> dict[str, Any] | None:
    day_s = day.isoformat()
    day_rows = [r for r in timeline_rows if r["m15"]["ts"].startswith(day_s)]
    pvm = _pvm_at_open(day_rows)
    as_of = datetime.datetime.combine(day, datetime.time(9, 15))
    bars_1m = iter_kbars_in_range(
        code, day - datetime.timedelta(days=5), day, cache_dir=cache_dir
    )
    bars_1m = [b for b in bars_1m if b.ts <= as_of]
    if not bars_1m:
        return None
    levels = compute_liquidity_levels(bars_1m, day, or_minutes=30)
    if not levels.or_range.valid:
        return None
    bars_15m = _day_bars_from_disk(code, day, 15, "both", cache_dir=cache_dir)
    bars_15m = [
        b
        for b in bars_15m
        if datetime.time(8, 45) <= b.ts.time() <= datetime.time(13, 45)
    ]
    bars_5m = _day_bars_from_disk(code, day, 5, "day", cache_dir=cache_dir)
    bars_5m = [b for b in bars_5m if b.ts.time() <= datetime.time(13, 30)]
    pools: list[tuple[str, float]] = [("or_low", levels.or_range.low)]
    if levels.dawn_low is not None:
        pools.append(("dawn_low", levels.dawn_low))
    if levels.overnight_low is not None:
        pools.append(("overnight_low", levels.overnight_low))
    return {
        "pvm": pvm,
        "or_high": levels.or_range.high,
        "or_low": levels.or_range.low,
        "bars_15m": bars_15m,
        "bars_5m": bars_5m,
        "pools": pools,
        "regime_tag": regime_by_day.get(day_s, "unknown"),
    }


def iter_a_plus_grid() -> list[APlusParams]:
    """Small grid: h4 fixed dual_above; h1 × stop × hold."""
    out: list[APlusParams] = []
    for h1, stop, hold in itertools.product(
        ("none", "not_below"),
        ("or_high_minus_30", "or_mid", "or_low"),
        (3, 5),
    ):
        out.append(APlusParams(h4="dual_above", h1=h1, stop=stop, hold_bars=hold))  # type: ignore[arg-type]
    return out


def iter_c_plus_grid() -> list[CPlusParams]:
    out: list[CPlusParams] = []
    for pool, buf in itertools.product(
        ("any", "or_only", "pools_pref"),
        (0.0, 20.0),
    ):
        out.append(CPlusParams(h4="dual_above", pool=pool, stop_buffer=buf))  # type: ignore[arg-type]
    return out


def iter_a_minus_grid() -> list[AMinusParams]:
    out: list[AMinusParams] = []
    for h4, h1, stop in itertools.product(
        ("dual_below",),
        ("none", "require_below"),
        ("or_high_plus_20", "or_mid", "bar_high_plus_20"),
    ):
        out.append(AMinusParams(h4=h4, h1=h1, stop=stop))  # type: ignore[arg-type]
    return out


def preload_day_contexts(
    timeline: dict[str, Any],
    *,
    code: str,
    cache_dir: Path,
    regime_by_day: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Load OR/bars/pvm once per day — shared across all grid variants."""
    out: dict[str, dict[str, Any]] = {}
    for day_s in _day_list_from_timeline(timeline):
        day = datetime.date.fromisoformat(day_s)
        ctx = _load_day_context(
            code,
            day,
            timeline["rows"],
            cache_dir=cache_dir,
            regime_by_day=regime_by_day,
        )
        if ctx is not None:
            out[day_s] = ctx
    return out


def run_variant(
    *,
    day_contexts: dict[str, dict[str, Any]],
    code: str,
    cache_dir: Path,
    family: str,
    params: APlusParams | CPlusParams | AMinusParams,
) -> dict[str, Any]:
    """Emit then score one param variant. ``day_contexts`` must be preloaded."""
    cands: list[dict[str, Any]] = []
    for day_s, ctx in day_contexts.items():
        day = datetime.date.fromisoformat(day_s)
        sig: dict[str, Any] | None = None
        if family == "A+" and isinstance(params, APlusParams):
            sig = scan_a_plus_long(
                day,
                bars_15m=ctx["bars_15m"],
                bars_5m=ctx["bars_5m"],
                or_high=ctx["or_high"],
                or_low=ctx["or_low"],
                pvm=ctx["pvm"],
                params=params,
                regime_tag=ctx["regime_tag"],
            )
        elif family == "C+" and isinstance(params, CPlusParams):
            sig = scan_c_plus_long(
                day,
                bars_15m=ctx["bars_15m"],
                bars_5m=ctx["bars_5m"],
                pools=list(ctx["pools"]),  # copy — scanners may rebind/filter
                pvm=ctx["pvm"],
                params=params,
                regime_tag=ctx["regime_tag"],
            )
        elif family == "A-+" and isinstance(params, AMinusParams):
            sig = scan_a_minus_short(
                day,
                bars_15m=ctx["bars_15m"],
                or_high=ctx["or_high"],
                or_low=ctx["or_low"],
                pvm=ctx["pvm"],
                params=params,
                regime_tag=ctx["regime_tag"],
            )
        if sig is not None:
            cands.append(sig)

    scored = [score_candidate(c, code=code, cache_dir=cache_dir) for c in cands]
    agg = aggregate_stories(scored)
    fam_key = _FAMILY_AGG_KEY.get(family)
    summary = (
        agg.get(fam_key, {"n": 0, "kills": ["no_trades"]})
        if fam_key
        else {"n": 0, "kills": ["no_trades"]}
    )
    return {
        "family": family,
        "variant": params.key(),
        "n": len(scored),
        "summary": summary,
        "candidates": scored,
        "passes_soft_success": _passes_soft(summary, len(scored)),
    }


def _passes_soft(summary: dict[str, Any], n: int) -> bool:
    """Soft winner gate: aggregate kill shape + path_support > 0.

    Uses shared ``FRICTION_BUFFER_PRIMARY`` / ``STOP_HIT_30_KILL``. Stricter than
    ``primary_eligible`` alone by requiring at least one path-supported event.
    """
    if n < 5:
        return False
    med = summary.get("median_path_edge_60m")
    if med is None or med < FRICTION_BUFFER_PRIMARY:
        return False
    stop30 = summary.get("stop_hit_30m_rate")
    if stop30 is not None and stop30 > STOP_HIT_30_KILL:
        return False
    support = summary.get("path_support_rate") or 0.0
    if support <= 0:
        return False
    return True


def run_tune(
    *,
    timeline_path: Path | None = None,
    regime_path: Path | None = None,
    out_path: Path | None = None,
    code: str = "TMFR1",
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4] / "workspaces" / "osf-baseline"
    timeline_path = timeline_path or (
        root / "reports" / "timeline_15m_2026-06-01_2026-06-30.json"
    )
    regime_path = regime_path or (root / "june_regime_map.json")
    out_path = out_path or (root / "june_2026_tune_results.json")

    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    regimes = json.loads(regime_path.read_text(encoding="utf-8"))
    regime_by_day = {r["day"]: r["regime"] for r in regimes}
    day_contexts = preload_day_contexts(
        timeline,
        code=code,
        cache_dir=cache_dir,
        regime_by_day=regime_by_day,
    )

    results: list[dict[str, Any]] = []
    for p in iter_a_plus_grid():
        results.append(
            run_variant(
                day_contexts=day_contexts,
                code=code,
                cache_dir=cache_dir,
                family="A+",
                params=p,
            )
        )
    for p in iter_c_plus_grid():
        results.append(
            run_variant(
                day_contexts=day_contexts,
                code=code,
                cache_dir=cache_dir,
                family="C+",
                params=p,
            )
        )
    for p in iter_a_minus_grid():
        results.append(
            run_variant(
                day_contexts=day_contexts,
                code=code,
                cache_dir=cache_dir,
                family="A-+",
                params=p,
            )
        )

    # Strip heavy candidate lists from non-winners for smaller JSON; keep all summaries
    compact = []
    winners = []
    for r in results:
        entry = {
            "family": r["family"],
            "variant": r["variant"],
            "n": r["n"],
            "summary": r["summary"],
            "passes_soft_success": r["passes_soft_success"],
        }
        compact.append(entry)
        if r["passes_soft_success"]:
            winners.append({**entry, "candidates": r["candidates"]})

    # Best by family (highest med edge among n>=3)
    best_by_family: dict[str, Any] = {}
    for r in results:
        fam = r["family"]
        med = r["summary"].get("median_path_edge_60m")
        n = r["n"]
        if n < 3 or med is None:
            continue
        prev = best_by_family.get(fam)
        if prev is None or med > prev["summary"].get("median_path_edge_60m", -1e9):
            best_by_family[fam] = {
                "variant": r["variant"],
                "n": n,
                "summary": r["summary"],
                "passes_soft_success": r["passes_soft_success"],
            }

    payload = {
        "status": "Research exploration (2026-06 only) — STORY TUNE",
        "not": "Pilot / UAT / Holdout / expectancy. One June pass only.",
        "friction_buffer_primary": FRICTION_BUFFER_PRIMARY,
        "timeline": str(timeline_path),
        "n_days_with_context": len(day_contexts),
        "n_variants": len(compact),
        "variants": compact,
        "winners": winners,
        "best_by_family": best_by_family,
        "baseline_ref": {
            "A|long": {"n": 6, "med_edge": -102.5, "support": 0.333},
            "C|long": {"n": 9, "med_edge": -178.0, "support": 0.111},
            "A-|short": {"n": 7, "med_edge": -250.0, "support": 0.143},
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    out = run_tune()
    print(f"variants={out['n_variants']} winners={len(out['winners'])}")
    print("best_by_family:", json.dumps(out["best_by_family"], ensure_ascii=False, indent=2))
