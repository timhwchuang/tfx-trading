"""MFE / horizon context analysis for corpse entries (FT-006 exemplar)."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from reporting.forward_pnl import load_tick_series
from reporting.post_entry_diagnosis import enrich_rows_with_forward_windows


def _med(xs: list[float]) -> float | None:
    return round(float(statistics.median(xs)), 2) if xs else None


def _mean(xs: list[float]) -> float | None:
    return round(float(statistics.mean(xs)), 2) if xs else None


def _bucket_z(z: float) -> str:
    az = abs(z)
    if az < 2.25:
        return "z_2.0_2.25"
    if az < 2.75:
        return "z_2.25_2.75"
    return "z_2.75_plus"


def analyze_vsf_entries(
    payload: dict[str, Any],
    *,
    stretch_k: str,
    cache_dir: Path,
) -> dict[str, Any]:
    entries = (payload.get("entries") or {}).get(stretch_k) or []
    if not entries:
        raise ValueError(f"no entries for k={stretch_k}")

    code = str(payload.get("code") or "TMFR1")
    from datetime import date

    if entries[0].get("day"):
        dates_sorted = sorted({e["day"] for e in entries if e.get("day")})
        day_objs = [date.fromisoformat(d) for d in dates_sorted]
    else:
        day_objs = []  # filled below
        from storage.tick_loader import resolve_cli_tick_cache_dates

        day_objs = sorted(
            resolve_cli_tick_cache_dates(
                explicit=None,
                from_cache=True,
                code=code,
                cache_dir=cache_dir,
                from_date=str(payload["from_date"]),
                to_date=str(payload["to_date"]),
            )
            or []
        )
    series = load_tick_series(code, day_objs, cache_dir=cache_dir)
    work = [dict(e) for e in entries]
    enrich_rows_with_forward_windows(work, series)

    # Per-trade derived metrics
    trades: list[dict[str, Any]] = []
    for r in work:
        fwd = r.get("post_entry_forward") or {}
        w5 = (fwd.get("W300") or {}).get("close_delta", 0.0)
        w15 = (fwd.get("W900") or {}).get("close_delta", 0.0)
        w30 = (fwd.get("W1800") or {}).get("close_delta", 0.0)
        sim = r.get("atr_barrier_sim") or {}
        mfe = float(sim.get("mfe") or 0)
        mae = float(sim.get("mae") or 0)
        trades.append(
            {
                **r,
                "w5": w5,
                "w15": w15,
                "w30": w30,
                "giveback_w5_to_w30": round(w5 - w30, 2),
                "mfe_mae_ratio": round(mfe / mae, 2) if mae > 0 else None,
                "z_bucket": _bucket_z(float(r.get("z") or 0)),
            }
        )

    mfes = [
        float((t.get("atr_barrier_sim") or {}).get("mfe") or 0)
        for t in trades
        if (t.get("atr_barrier_sim") or {}).get("mfe") is not None
    ]
    mfe_p75 = float(statistics.quantiles(mfes, n=4)[2]) if len(mfes) >= 4 else max(mfes, default=0)

    high_mfe = [t for t in trades if float((t.get("atr_barrier_sim") or {}).get("mfe") or 0) >= mfe_p75]

    def _cohort(rows: list[dict]) -> dict[str, Any]:
        if not rows:
            return {"n": 0}
        return {
            "n": len(rows),
            "barrier_net_median": _med([float(r["net_atr_sim"]) for r in rows]),
            "w5_median": _med([float(r["w5"]) for r in rows]),
            "w15_median": _med([float(r["w15"]) for r in rows]),
            "w30_median": _med([float(r["w30"]) for r in rows]),
            "giveback_median": _med([float(r["giveback_w5_to_w30"]) for r in rows]),
            "mfe_median": _med(
                [float((r.get("atr_barrier_sim") or {}).get("mfe") or 0) for r in rows]
            ),
            "mae_median": _med(
                [float((r.get("atr_barrier_sim") or {}).get("mae") or 0) for r in rows]
            ),
            "mfe_mae_ratio_median": _med(
                [float(r["mfe_mae_ratio"]) for r in rows if r.get("mfe_mae_ratio")]
            ),
        }

    by_bucket: dict[str, Any] = {}
    for dim in ("session_bucket", "direction", "z_bucket"):
        groups: dict[str, list] = defaultdict(list)
        for t in trades:
            groups[str(t.get(dim, "?"))].append(t)
        by_bucket[dim] = {k: _cohort(v) for k, v in sorted(groups.items())}

    # Horizon decay (aggregate)
    horizon_decay = {
        "w5_median": _med([float(t["w5"]) for t in trades]),
        "w15_median": _med([float(t["w15"]) for t in trades]),
        "w30_median": _med([float(t["w30"]) for t in trades]),
        "giveback_w5_to_w30_median": _med([float(t["giveback_w5_to_w30"]) for t in trades]),
        "pct_w5_positive": round(
            100 * sum(1 for t in trades if t["w5"] > 0) / len(trades), 1
        ),
        "pct_w30_positive": round(
            100 * sum(1 for t in trades if t["w30"] > 0) / len(trades), 1
        ),
    }

    return {
        "stretch_k": stretch_k,
        "n": len(trades),
        "mfe_p75_threshold": round(mfe_p75, 2),
        "high_mfe_cohort": _cohort(high_mfe),
        "high_mfe_by_session": {
            str(t.get("session_bucket")): str(t.get("direction"))
            for t in high_mfe[:5]
        },
        "horizon_decay": horizon_decay,
        "by_dimension": by_bucket,
        "interpretation": [
            "W5→W30 遞減 = 早段順向後被回吐（fade 典型）；非傳統固定 SL/TP 風報比。",
            "風報比請看 mfe_mae_ratio（路徑內最大順/逆），非 W5/W15/W30 三點。",
            "高 MFE 子集若 barrier 仍負 → 出場/持有時間問題；若 W30 也負 → 方向錯。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "json_path",
        type=Path,
        default=root / "workspaces/vsf-baseline/reports/counterfactual_v2.1_train2025.json",
        nargs="?",
    )
    parser.add_argument("--stretch-k", default="2.0")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    result = analyze_vsf_entries(
        payload,
        stretch_k=args.stretch_k,
        cache_dir=root / "tick_cache",
    )
    out = args.output or args.json_path.with_name(
        f"mfe_context_k{args.stretch_k.replace('.', 'p')}.json"
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
