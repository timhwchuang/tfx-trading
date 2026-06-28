"""Standard post-entry diagnosis for Phase 0 counterfactuals (FT-012+).

Answers: after entry, did price move in our direction (stop-less windows, MFE/MAE)?
Separate from barrier/exit PnL used for gate G1–G2.

Not a gate criterion — appendix only. See ALPHA_RESEARCH_PLAYBOOK §2 Phase 0c.
"""

from __future__ import annotations

import bisect
import statistics
from typing import Any

from reporting.forward_pnl import TickSeries, _direction_sign

STANDARD_FORWARD_WINDOWS_SEC = (300, 900, 1800)  # W5 / W15 / W30 minutes

INTERPRETATION_NOTE = (
    "stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。"
)


def entry_window_stats(
    entry_price: float,
    entry_ts: int,
    direction: str,
    series: TickSeries,
    window_sec: int,
    *,
    atr: float | None = None,
) -> dict[str, float]:
    """Signed close_delta, MFE, MAE over [entry_ts, entry_ts + window_sec]."""
    if not series.timestamps:
        return {
            "close_delta": 0.0,
            "MFE_delta": 0.0,
            "MAE_delta": 0.0,
            "signed_return_over_atr": 0.0,
        }

    sign = _direction_sign(direction)
    start_idx = bisect.bisect_left(series.timestamps, entry_ts)
    if start_idx >= len(series.timestamps):
        start_idx = len(series.timestamps) - 1

    target_ts = entry_ts + window_sec
    end_idx = bisect.bisect_right(series.timestamps, target_ts) - 1
    end_idx = max(start_idx, min(len(series.timestamps) - 1, end_idx))

    mfe = float("-inf")
    mae = float("-inf")
    for i in range(start_idx, end_idx + 1):
        delta = sign * (series.closes[i] - entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)

    close_delta = sign * (series.closes[end_idx] - entry_price)
    atr_denom = atr if atr and atr > 0 else None
    return {
        "close_delta": round(close_delta, 2),
        "MFE_delta": round(mfe if mfe != float("-inf") else 0.0, 2),
        "MAE_delta": round(mae if mae != float("-inf") else 0.0, 2),
        "signed_return_over_atr": round(close_delta / atr_denom, 4) if atr_denom else 0.0,
    }


def enrich_rows_with_forward_windows(
    rows: list[dict[str, Any]],
    series: TickSeries,
    *,
    windows_sec: tuple[int, ...] = STANDARD_FORWARD_WINDOWS_SEC,
    direction_key: str = "direction",
    price_key: str = "entry_price",
    ts_key: str = "ts",
    atr_key: str = "atr",
) -> None:
    """Attach per-row ``post_entry_forward`` keyed W{seconds}. Mutates rows in place."""
    for row in rows:
        direction = str(row.get(direction_key, "Long"))
        price = float(row[price_key])
        ts = int(row[ts_key])
        atr = float(row[atr_key]) if row.get(atr_key) is not None else None
        fwd: dict[str, dict[str, float]] = {}
        for w in windows_sec:
            fwd[f"W{w}"] = entry_window_stats(
                price, ts, direction, series, w, atr=atr
            )
        row["post_entry_forward"] = fwd


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.mean(values)), 2)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 2)


def _barrier_mfe_mae(row: dict[str, Any]) -> tuple[float | None, float | None]:
    sim = row.get("atr_barrier_sim") or row.get("scalp_sim")
    if not isinstance(sim, dict):
        return None, None
    mfe = sim.get("mfe")
    mae = sim.get("mae")
    return (
        float(mfe) if mfe is not None else None,
        float(mae) if mae is not None else None,
    )


def _summarize_row_subset(
    rows: list[dict[str, Any]],
    *,
    friction_points: float,
    barrier_gross_key: str,
    barrier_net_key: str,
    windows_sec: tuple[int, ...],
) -> dict[str, Any]:
    if not rows:
        return {"n": 0}

    barrier_gross = [float(r[barrier_gross_key]) for r in rows if barrier_gross_key in r]
    barrier_net = [float(r[barrier_net_key]) for r in rows if barrier_net_key in r]
    mfes: list[float] = []
    maes: list[float] = []
    for r in rows:
        mfe, mae = _barrier_mfe_mae(r)
        if mfe is not None:
            mfes.append(mfe)
        if mae is not None:
            maes.append(mae)

    forward: dict[str, dict[str, Any]] = {}
    for w in windows_sec:
        key = f"W{w}"
        closes: list[float] = []
        w_mfes: list[float] = []
        w_maes: list[float] = []
        for r in rows:
            block = (r.get("post_entry_forward") or {}).get(key) or {}
            if "close_delta" in block:
                closes.append(float(block["close_delta"]))
            if "MFE_delta" in block:
                w_mfes.append(float(block["MFE_delta"]))
            if "MAE_delta" in block:
                w_maes.append(float(block["MAE_delta"]))
        forward[key] = {
            "close_delta_mean": _mean(closes),
            "close_delta_median": _median(closes),
            "net_median": (
                round(_median(closes) - friction_points, 2)  # type: ignore[operator]
                if _median(closes) is not None
                else None
            ),
            "MFE_median": _median(w_mfes),
            "MAE_median": _median(w_maes),
        }

    return {
        "n": len(rows),
        "barrier": {
            "gross_mean": _mean(barrier_gross),
            "gross_median": _median(barrier_gross),
            "net_mean": _mean(barrier_net),
            "net_median": _median(barrier_net),
        },
        "barrier_path": {
            "MFE_mean": _mean(mfes),
            "MFE_median": _median(mfes),
            "MAE_mean": _mean(maes),
            "MAE_median": _median(maes),
        },
        "forward": forward,
    }


def interpret_post_entry(
    summary: dict[str, Any],
    *,
    friction_points: float,
) -> dict[str, Any]:
    """Heuristic verdict — diagnostic only, not gate."""
    notes: list[str] = []
    n = int(summary.get("n") or 0)
    if n < 5:
        return {"verdict": "insufficient_n", "notes": ["n < 5"]}

    barrier = summary.get("barrier") or {}
    fwd = summary.get("forward") or {}
    path = summary.get("barrier_path") or {}
    w30 = fwd.get("W1800") or {}
    w15 = fwd.get("W900") or {}

    b_med = barrier.get("gross_median")
    w30_med = w30.get("close_delta_median")
    w15_med = w15.get("close_delta_median")
    mfe_med = path.get("MFE_median")
    mae_med = path.get("MAE_median")

    verdict = "ambiguous"

    if w30_med is not None and w30_med >= friction_points + 2 and (b_med or 0) < 0:
        verdict = "exit_kills_edge"
        notes.append("W30 stop-less median 可覆蓋摩擦，但 barrier median 為負 → 出場/停損殺 edge")
    elif w30_med is not None and w30_med < 0 and (b_med or 0) < 0:
        verdict = "direction_failed"
        notes.append("W30 stop-less median 為負 → 方向假說弱")
    elif w30_med is not None and 0 <= w30_med < friction_points:
        verdict = "direction_weak"
        notes.append(f"W30 median {w30_med} 撐不過摩擦 {friction_points} 點")
    elif w30_med is not None and w30_med >= friction_points:
        verdict = "direction_ok_margin_thin"
        notes.append("W30 stop-less 有正 median，仍須看 barrier 與 valid")

    if mfe_med is not None and mae_med is not None:
        if mfe_med > mae_med:
            notes.append(f"180s 內 MFE median {mfe_med} > MAE {mae_med}（路徑曾順向）")
        else:
            notes.append(f"180s 內 MAE median {mae_med} ≥ MFE {mfe_med}（逆風路徑主導）")

    if w15_med is not None and w30_med is not None and w15_med < 0 <= w30_med:
        notes.append("W15 負、W30 正 → 需較長持有才 revert；與短 barrier 衝突")

    return {"verdict": verdict, "notes": notes, "policy_note": INTERPRETATION_NOTE}


def summarize_post_entry_diagnosis(
    rows: list[dict[str, Any]],
    *,
    friction_points: float,
    barrier_gross_key: str = "gross_atr_sim",
    barrier_net_key: str = "net_atr_sim",
    direction_key: str = "direction",
    windows_sec: tuple[int, ...] = STANDARD_FORWARD_WINDOWS_SEC,
) -> dict[str, Any]:
    """Aggregate post-entry stats for one param cohort."""
    overall = _summarize_row_subset(
        rows,
        friction_points=friction_points,
        barrier_gross_key=barrier_gross_key,
        barrier_net_key=barrier_net_key,
        windows_sec=windows_sec,
    )
    by_dir: dict[str, Any] = {}
    for direction in sorted({str(r.get(direction_key, "Long")) for r in rows}):
        subset = [r for r in rows if str(r.get(direction_key)) == direction]
        by_dir[direction] = _summarize_row_subset(
            subset,
            friction_points=friction_points,
            barrier_gross_key=barrier_gross_key,
            barrier_net_key=barrier_net_key,
            windows_sec=windows_sec,
        )

    overall["by_direction"] = by_dir
    overall["interpretation"] = interpret_post_entry(overall, friction_points=friction_points)
    return overall


def format_gate_report_post_entry_section(
    diagnosis: dict[str, Any],
    *,
    param_label: str,
) -> list[str]:
    """Markdown lines for gate_report.md appendix."""
    lines = [
        f"## 進場後診斷（{param_label} · 非 gate）",
        "",
        f"> {INTERPRETATION_NOTE}",
        "",
        "| 指標 | mean | median |",
        "|------|------|--------|",
    ]
    barrier = diagnosis.get("barrier") or {}
    lines.append(
        f"| Barrier gross | {barrier.get('gross_mean', '—')} | "
        f"{barrier.get('gross_median', '—')} |"
    )
    path = diagnosis.get("barrier_path") or {}
    lines.append(
        f"| 180s MFE / MAE | {path.get('MFE_mean', '—')} / {path.get('MAE_mean', '—')} | "
        f"{path.get('MFE_median', '—')} / {path.get('MAE_median', '—')} |"
    )
    for w in STANDARD_FORWARD_WINDOWS_SEC:
        key = f"W{w}"
        label = f"W{w // 60}m stop-less gross"
        block = (diagnosis.get("forward") or {}).get(key) or {}
        lines.append(
            f"| {label} | {block.get('close_delta_mean', '—')} | "
            f"{block.get('close_delta_median', '—')} (net med {block.get('net_median', '—')}) |"
        )

    interp = diagnosis.get("interpretation") or {}
    lines.extend(["", f"**Verdict**: `{interp.get('verdict', '—')}`", ""])
    for note in interp.get("notes") or []:
        lines.append(f"- {note}")

    by_dir = diagnosis.get("by_direction") or {}
    if by_dir:
        lines.extend(["", "### Long / Short", "", "| side | n | barrier med | W30 med |", "|---|---:|---:|---:|"])
        for side, block in sorted(by_dir.items()):
            b = (block.get("barrier") or {}).get("gross_median", "—")
            w30 = ((block.get("forward") or {}).get("W1800") or {}).get("close_delta_median", "—")
            lines.append(f"| {side} | {block.get('n', 0)} | {b} | {w30} |")

    lines.append("")
    return lines
