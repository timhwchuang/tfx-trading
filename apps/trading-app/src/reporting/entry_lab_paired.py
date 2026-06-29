"""GDC barrier vs GUDT trail paired autopsy."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _pair_key(row: dict[str, Any]) -> tuple[str, int, float]:
    return (str(row["day"]), int(row["ts"]), round(float(row["entry_price"]), 1))


def paired_gdc_gudt(
    gdc_rows: list[dict[str, Any]],
    gudt_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    gdc_by = {_pair_key(r): r for r in gdc_rows}
    gudt_by = {_pair_key(r): r for r in gudt_rows}
    keys = sorted(set(gdc_by) & set(gudt_by))
    if not keys:
        return {"n_paired": 0}

    deltas: list[dict[str, Any]] = []
    barrier_reasons: list[str] = []
    trail_reasons: list[str] = []
    transitions: Counter[tuple[str, str]] = Counter()

    for k in keys:
        g, u = gdc_by[k], gudt_by[k]
        bsim = g.get("atr_barrier_sim") or {}
        tsim = u.get("atr_trail_sim") or {}
        br = str(bsim.get("exit_reason") or "unknown")
        tr = str(tsim.get("exit_reason") or "unknown")
        barrier_reasons.append(br)
        trail_reasons.append(tr)
        transitions[(br, tr)] += 1

        def _w(row: dict[str, Any], wkey: str) -> float | None:
            block = (row.get("post_entry_forward") or {}).get(wkey) or {}
            v = block.get("close_delta")
            return float(v) if v is not None else None

        deltas.append(
            {
                "day": k[0],
                "ts": k[1],
                "delta_w900": _delta(_w(g, "W900"), _w(u, "W900")),
                "delta_net": round(float(g.get("net_atr_sim", 0)) - float(u.get("net_atr_sim", 0)), 2),
                "barrier_net": float(g.get("net_atr_sim", 0)),
                "trail_net": float(u.get("net_atr_sim", 0)),
                "barrier_reason": br,
                "trail_reason": tr,
            }
        )

    path_flip = sum(
        1 for d in deltas if (d["barrier_net"] <= 0 < d["trail_net"]) or (d["trail_net"] <= 0 < d["barrier_net"])
    )
    return {
        "n_paired": len(keys),
        "delta_net_median": _median([d["delta_net"] for d in deltas]),
        "path_contract_flip_count": path_flip,
        "exit_transition_top": [
            {"barrier": a, "trail": b, "n": c}
            for (a, b), c in transitions.most_common(10)
        ],
        "per_entry": deltas,
        "note": "Paired on (day, ts, entry_price). Selection: GUDT long-only subset of GDC-eligible days.",
    }


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    m = len(xs) // 2
    if len(xs) % 2:
        return round(xs[m], 2)
    return round((xs[m - 1] + xs[m]) / 2, 2)
