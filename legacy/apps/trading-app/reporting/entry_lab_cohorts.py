"""Cohort statistics and bootstrap for Entry Lab."""

from __future__ import annotations

import random
import statistics
from typing import Any, Callable

from reporting.entry_lab_config import BOOTSTRAP_N, BOOTSTRAP_SEED

FORWARD_KEYS = ("W300", "W900", "W1800")


def _med(xs: list[float]) -> float | None:
    return round(float(statistics.median(xs)), 2) if xs else None


def _pct_positive(xs: list[float]) -> float | None:
    if not xs:
        return None
    return round(100.0 * sum(1 for x in xs if x > 0) / len(xs), 1)


def _window_delta(row: dict[str, Any], key: str, field: str = "close_delta") -> float | None:
    block = (row.get("post_entry_forward") or {}).get(key) or {}
    v = block.get(field)
    return float(v) if v is not None else None


def _sim_mfe_mae(row: dict[str, Any]) -> tuple[float | None, float | None]:
    for k in ("atr_barrier_sim", "atr_trail_sim", "fvg_mid_trail_sim"):
        sim = row.get(k)
        if isinstance(sim, dict) and sim.get("mfe") is not None:
            return float(sim["mfe"]), float(sim.get("mae") or 0)
    return None, None


def derived_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    w5 = _window_delta(row, "W300")
    w30 = _window_delta(row, "W1800")
    mfe, mae = _sim_mfe_mae(row)
    gross = float(row.get("gross_atr_sim") or 0)
    giveback = round(w5 - w30, 2) if w5 is not None and w30 is not None else None
    exit_gap = round(mfe - gross, 2) if mfe is not None else None
    ratio = round(mfe / mae, 2) if mfe is not None and mae and mae > 0 else None
    return {
        "w5": w5,
        "w15": _window_delta(row, "W900"),
        "w30": w30,
        "giveback_w5_to_w30": giveback,
        "exit_gap": exit_gap,
        "mfe_mae_ratio": ratio,
    }


def attach_derived(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        r["derived"] = derived_metrics(r)


def sample_tier(n: int) -> str:
    if n >= 30:
        return "descriptive_ci"
    if n >= 15:
        return "descriptive_only"
    if n >= 10:
        return "hypothesis_only"
    return "underpowered"


def mde_note(n: int, p0: float | None) -> str | None:
    if p0 is None or n < 5:
        return None
    # Approx n for 15pp lift at 80% power (normal approx)
    p1 = min(0.99, p0 + 0.15)
    p_bar = (p0 + p1) / 2
    z_alpha, z_beta = 1.96, 0.84
    num = z_alpha * (2 * p_bar * (1 - p_bar)) ** 0.5 + z_beta * (
        p0 * (1 - p0) + p1 * (1 - p1)
    ) ** 0.5
    denom = abs(p1 - p0)
    if denom < 1e-9:
        return None
    n_need = int((num / denom) ** 2) + 1
    if n < n_need:
        return f"underpowered_for_15pp_need_n~{n_need}"
    return None


def bootstrap_median_ci(
    values: list[float],
    *,
    n_resamples: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float | None]:
    if len(values) < 2:
        med = _med(values)
        return {"median": med, "ci_low": med, "ci_high": med}
    rng = random.Random(seed)
    meds: list[float] = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        meds.append(float(statistics.median(sample)))
    meds.sort()
    lo = meds[int(0.025 * len(meds))]
    hi = meds[int(0.975 * len(meds)) - 1]
    return {
        "median": _med(values),
        "ci_low": round(lo, 2),
        "ci_high": round(hi, 2),
    }


def summarize_cohort(rows: list[dict[str, Any]], *, friction: float = 5.0) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "tier": "underpowered"}

    w5s = [_window_delta(r, "W300") for r in rows]
    w15s = [_window_delta(r, "W900") for r in rows]
    w30s = [_window_delta(r, "W1800") for r in rows]
    w5s = [x for x in w5s if x is not None]
    w15s = [x for x in w15s if x is not None]
    w30s = [x for x in w30s if x is not None]

    gross = [float(r["gross_atr_sim"]) for r in rows if "gross_atr_sim" in r]
    net = [float(r["net_atr_sim"]) for r in rows if "net_atr_sim" in r]
    mfes, maes, gaps = [], [], []
    for r in rows:
        d = r.get("derived") or derived_metrics(r)
        mfe, mae = _sim_mfe_mae(r)
        if mfe is not None:
            mfes.append(mfe)
        if mae is not None:
            maes.append(mae)
        if d.get("exit_gap") is not None:
            gaps.append(float(d["exit_gap"]))

    p0 = (_pct_positive(w30s) or 0) / 100.0 if w30s else None
    n = len(rows)
    tier = sample_tier(n)

    out: dict[str, Any] = {
        "n": n,
        "tier": tier,
        "mde_note": mde_note(n, p0),
        "path": {
            "pct_w5_pos": _pct_positive(w5s),
            "pct_w15_pos": _pct_positive(w15s),
            "pct_w30_pos": _pct_positive(w30s),
            "w5_median": _med(w5s),
            "w15_median": _med(w15s),
            "w30_median": _med(w30s),
        },
        "contract": {
            "gross_median": _med(gross),
            "net_median": _med(net),
            "pct_net_pos": _pct_positive(net),
            "mfe_median": _med(mfes),
            "mae_median": _med(maes),
            "exit_gap_median": _med(gaps),
        },
    }
    if tier == "descriptive_ci" and w30s:
        out["path"]["w30_bootstrap_ci"] = bootstrap_median_ci(w30s)
    return out


def cohort_by_key(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        k = key_fn(r)
        groups.setdefault(k, []).append(r)
    return {k: summarize_cohort(v) for k, v in sorted(groups.items())}


def filter_intersection_matrix(
    filters: dict[str, set[tuple[str, int]]],
) -> dict[str, Any]:
    """Jaccard overlap between filter keep-sets (day, ts)."""
    names = sorted(filters.keys())
    matrix: dict[str, dict[str, float | None]] = {}
    for a in names:
        matrix[a] = {}
        for b in names:
            sa, sb = filters[a], filters[b]
            if not sa and not sb:
                matrix[a][b] = None
            elif not sa or not sb:
                matrix[a][b] = 0.0
            else:
                inter = len(sa & sb)
                union = len(sa | sb)
                matrix[a][b] = round(inter / union, 3) if union else None
    return {"jaccard": matrix, "filter_names": names}


def entry_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("day", "")), int(row["ts"]))
