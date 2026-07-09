"""Robustness checks for Entry Lab (appendix only)."""

from __future__ import annotations

import random
import statistics
from typing import Any

from reporting.entry_lab_cohorts import _window_delta
from reporting.entry_lab_config import BOOTSTRAP_SEED, FRICTION_ROBUST


def friction_sensitivity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    gross = [float(r["gross_atr_sim"]) for r in rows]
    net5 = [g - 5.0 for g in gross]
    net7 = [g - FRICTION_ROBUST for g in gross]
    pos5 = sum(1 for x in net5 if x > 0) / len(net5)
    pos7 = sum(1 for x in net7 if x > 0) / len(net7)
    return {
        "n": len(rows),
        "pct_net_pos_friction_5": round(100 * pos5, 1),
        "pct_net_pos_friction_7": round(100 * pos7, 1),
    }


def _with_minus_counter_median(
    rows: list[dict[str, Any]],
    labels: list[str],
) -> float | None:
    with_vals, counter_vals = [], []
    for r, lab in zip(rows, labels):
        v = _window_delta(r, "W1800")
        if v is None:
            continue
        if lab == "with_trend":
            with_vals.append(v)
        elif lab == "counter_trend":
            counter_vals.append(v)
    if not with_vals or not counter_vals:
        return None
    return float(statistics.median(with_vals) - statistics.median(counter_vals))


def regime_label_permutation_null(
    rows: list[dict[str, Any]],
    *,
    n_perm: int = 1000,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if len(rows) < 10:
        return {"n": len(rows), "skipped": "insufficient_n"}

    labels = [(r.get("alignment") or {}).get("r2", "neutral") for r in rows]
    observed = _with_minus_counter_median(rows, labels)
    if observed is None:
        return {"n": len(rows), "skipped": "no_with_counter_split"}

    rng = random.Random(seed)
    perm_diffs: list[float] = []
    for _ in range(n_perm):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        diff = _with_minus_counter_median(rows, shuffled)
        if diff is not None:
            perm_diffs.append(diff)
    if not perm_diffs:
        return {
            "observed_with_minus_counter_med": round(observed, 2),
            "skipped": "no_perm_samples",
        }

    perm_diffs.sort()
    rank = sum(1 for x in perm_diffs if abs(x) >= abs(observed))
    return {
        "observed_with_minus_counter_med": round(observed, 2),
        "perm_diff_p90": round(perm_diffs[int(0.9 * len(perm_diffs))], 2),
        "perm_exceeds_observed_pct": round(100.0 * rank / len(perm_diffs), 1),
        "exploratory_only": True,
    }
