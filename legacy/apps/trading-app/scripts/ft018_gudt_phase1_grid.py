"""Phase 1 CF grid: min_atr_pts × p0_ext_open_max × gap_k_atr (tune / holdout)."""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from reporting.gudt_wash_probe import (
    WashProbeTuning,
    _simulate_exit,
    load_probe_contexts,
    read_probe_csv,
    simulate_atr_trail_skew_exit,
    simulate_flow_bailout_exit,
)
from strategy_gudt_route_a.stack import RouteAStackParams, summarize_route_a_stack
from strategy_gudt_route_a.wash_bridge import BPrimeCompositeParams

TUNE_FROM = "2025-05-01"
TUNE_TO = "2025-12-31"
HOLD_FROM = "2026-01-01"
HOLD_TO = "2026-06-30"


@dataclass(frozen=True)
class GridPoint:
    min_atr_pts: float
    p0_ext_open_max: float | None
    gap_k_atr: float

    def key(self) -> str:
        po = "off" if self.p0_ext_open_max is None else f"{self.p0_ext_open_max:g}".replace(".", "p")
        ma = f"{self.min_atr_pts:g}".replace(".", "p")
        gk = f"{self.gap_k_atr:g}".replace(".", "p")
        return f"ma{ma}_p0{po}_gk{gk}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _slice_stats(picks: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    sub = [p for p in picks if start <= p["day"] <= end]
    nets = [float(p["net"]) for p in sub]
    if not nets:
        return {"n": 0, "net": 0.0, "wr": 0.0, "worst_month": 0.0, "avg": 0.0}
    by_m: dict[str, float] = {}
    wins = sum(1 for n in nets if n > 0)
    for p in sub:
        by_m[p["day"][:7]] = by_m.get(p["day"][:7], 0.0) + float(p["net"])
    worst = min(by_m.values()) if by_m else 0.0
    return {
        "n": len(sub),
        "net": round(sum(nets), 2),
        "wr": round(100.0 * wins / len(nets), 1),
        "worst_month": round(worst, 2),
        "avg": round(sum(nets) / len(nets), 2),
    }


def _patched_simulate_exit(min_atr_pts: float):
    @functools.wraps(_simulate_exit)
    def _wrap(entry, ctx, exit_mode):  # type: ignore[no-untyped-def]
        from reporting.gudt_wash_probe import (
            SEALED_BE,
            SEALED_HARD_TP,
            SEALED_K_SL,
            SEALED_MAX_HOLD,
            SEALED_TRAIL_ARM,
            SEALED_TRAIL_DIST,
            _resolve_stop_price,
        )

        initial_stop = _resolve_stop_price(entry, ctx, exit_mode)
        common = dict(
            direction="Long",
            entry_price=entry.entry_price,
            entry_ts=entry.entry_ts,
            atr=ctx.atr,
            ticks=ctx.ticks,
            min_atr_pts=min_atr_pts,
        )
        if exit_mode == "sealed":
            return simulate_atr_trail_skew_exit(
                **common,
                hard_stop_atr_k=SEALED_K_SL,
                be_trigger_atr_k=SEALED_BE,
                trail_arm_atr_k=SEALED_TRAIL_ARM,
                trail_dist_atr_k=SEALED_TRAIL_DIST,
                hard_tp_atr_k=SEALED_HARD_TP,
                max_hold_sec=SEALED_MAX_HOLD,
            )
        if exit_mode in ("wash_struct", "drive_low_struct"):
            return simulate_atr_trail_skew_exit(
                **common,
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
                min_atr_pts=min_atr_pts,
            )
        return _simulate_exit(entry, ctx, exit_mode)

    return _wrap


def _eval_grid_point(
    rows: list[dict[str, Any]],
    *,
    ctx_by_day: dict[str, Any],
    point: GridPoint,
) -> dict[str, Any]:
    import reporting.gudt_wash_probe as wp
    import strategy_gudt_route_a.wash_bridge as wb

    patched = _patched_simulate_exit(point.min_atr_pts)
    old_wp, old_wb = wp._simulate_exit, wb._simulate_exit
    wp._simulate_exit = patched  # type: ignore[method-assign]
    wb._simulate_exit = patched  # type: ignore[method-assign]
    try:
        params = RouteAStackParams(
            br5=BPrimeCompositeParams(
                pre_break_br_min=0.35,
                pre_break_br_p0_only=True,
                p0_ext_open_max=point.p0_ext_open_max,
                flip_min_ext_open=5.0,
            ),
        )
        summary = summarize_route_a_stack(rows, ctx_by_day=ctx_by_day, params=params)
    finally:
        wp._simulate_exit = old_wp  # type: ignore[method-assign]
        wb._simulate_exit = old_wb  # type: ignore[method-assign]

    picks = summary["picks"]
    return {
        "key": point.key(),
        "min_atr_pts": point.min_atr_pts,
        "p0_ext_open_max": point.p0_ext_open_max,
        "gap_k_atr": point.gap_k_atr,
        "tune": _slice_stats(picks, TUNE_FROM, TUNE_TO),
        "holdout": _slice_stats(picks, HOLD_FROM, HOLD_TO),
        "full_n": summary["n"],
        "skipped": summary["skipped"],
    }


def _naive_baselines(
    rows: list[dict[str, Any]],
    ctx_by_day: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compare GUDT edge vs always-on wash-day long baselines (CF, friction=5)."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)

    def _row_net(day_rows: list[dict[str, Any]], em: str, ex: str) -> float | None:
        for r in day_rows:
            if r["entry_mode"] == em and r["exit_mode"] == ex:
                return float(r["net"])
        return None

    fr = 5.0
    series: dict[str, list[tuple[str, float]]] = {
        "always_p0_sealed": [],
        "always_ft_dl": [],
        "oracle_best_row": [],
    }
    for day, day_rows in sorted(by_day.items()):
        if day not in ctx_by_day:
            continue
        p0 = _row_net(day_rows, "p0", "sealed")
        ft = _row_net(day_rows, "flow_turn", "drive_low_struct")
        if p0 is not None:
            series["always_p0_sealed"].append((day, p0 - fr))
        if ft is not None:
            series["always_ft_dl"].append((day, ft - fr))
        best = max(float(r["net"]) for r in day_rows) - fr
        series["oracle_best_row"].append((day, best))

    out: dict[str, dict[str, Any]] = {}
    for name, pts in series.items():
        for label, start, end in (
            ("tune", TUNE_FROM, TUNE_TO),
            ("holdout", HOLD_FROM, HOLD_TO),
        ):
            sub = [n for d, n in pts if start <= d <= end]
            key = f"{name}_{label}"
            out[key] = {
                "n": len(sub),
                "net": round(sum(sub), 2),
                "wr": round(100.0 * sum(1 for n in sub if n > 0) / len(sub), 1) if sub else 0.0,
            }
    return out


def _markdown_table(rows: list[dict[str, Any]], top: int = 15) -> str:
    lines = [
        "| rank | min_atr | p0_ext_max | gap_k | tune n | tune net | tune WR | worst mo | hold n | hold net | hold WR | score |",
        "|-----:|--------:|-----------:|------:|-------:|---------:|--------:|---------:|-------:|---------:|--------:|------:|",
    ]
    for i, r in enumerate(rows[:top], 1):
        t, h = r["tune"], r["holdout"]
        score = t["net"] + 0.5 * h["net"] - 2.0 * abs(min(0, t["worst_month"]))
        po = "—" if r["p0_ext_open_max"] is None else f"{r['p0_ext_open_max']:.1f}"
        lines.append(
            f"| {i} | {r['min_atr_pts']:.0f} | {po} | {r['gap_k_atr']:.1f} | "
            f"{t['n']} | {t['net']:+.0f} | {t['wr']:.0f}% | {t['worst_month']:+.0f} | "
            f"{h['n']} | {h['net']:+.0f} | {h['wr']:.0f}% | {score:+.0f} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="GUDT Route A phase-1 CF grid")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=root / "workspaces/gudt-baseline/reports/gudt_wash_probe_merged_202505_202606.csv",
    )
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=None)
    args = parser.parse_args(argv)

    rows = [r for r in read_probe_csv(args.from_csv) if TUNE_FROM <= r["day"] <= HOLD_TO]
    grid = [
        GridPoint(min_atr_pts=ma, p0_ext_open_max=po, gap_k_atr=gk)
        for ma, po, gk in itertools.product(
            (15.0, 25.0, 35.0),
            (None, 4.5, 5.5),
            (0.8, 1.0, 1.2),
        )
    ]

    days = sorted({r["day"] for r in rows})
    ctx_cache: dict[float, dict[str, Any]] = {}
    for gk in {p.gap_k_atr for p in grid}:
        ctx_cache[gk] = load_probe_contexts(
            "TMFR1", days, cache_dir=args.cache_dir, tuning=WashProbeTuning(gap_k_atr=gk)
        )

    results = [
        _eval_grid_point(rows, ctx_by_day=ctx_cache[p.gap_k_atr], point=p) for p in grid
    ]
    for r in results:
        t, h = r["tune"], r["holdout"]
        r["score"] = round(t["net"] + 0.5 * h["net"] - 2.0 * abs(min(0, t["worst_month"])), 2)
    results.sort(key=lambda x: (-x["score"], -x["holdout"]["net"]))

    default_ctx = load_probe_contexts("TMFR1", sorted({r["day"] for r in rows}), cache_dir=args.cache_dir)
    baselines = _naive_baselines(rows, default_ctx)
    default_row = next((r for r in results if r["min_atr_pts"] == 25 and r["p0_ext_open_max"] is None and r["gap_k_atr"] == 1.0), results[0])

    out_json = args.out_json or (
        root / "workspaces/gudt-baseline/reports/gudt_phase1_grid_tune202505_hold2026h1.json"
    )
    out_md = args.out_md or (
        root / "workspaces/gudt-baseline/reports/gudt_phase1_grid_tune202505_hold2026h1.md"
    )
    payload = {
        "tune": f"{TUNE_FROM}..{TUNE_TO}",
        "holdout": f"{HOLD_FROM}..{HOLD_TO}",
        "default": default_row,
        "baselines": baselines,
        "grid": results,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = [
        f"# GUDT Phase-1 grid — tune {TUNE_FROM}..{TUNE_TO} · holdout {HOLD_FROM}..{HOLD_TO}",
        "",
        "Axes: `min_atr_pts` × `p0_ext_open_max` × `gap_k_atr` (CF Route A stack, friction=5).",
        "",
        "## Default (ma25, p0 ext off, gk1.0)",
        "",
        f"- tune: n={default_row['tune']['n']} net={default_row['tune']['net']:+.1f} WR={default_row['tune']['wr']:.0f}%",
        f"- holdout: n={default_row['holdout']['n']} net={default_row['holdout']['net']:+.1f} WR={default_row['holdout']['wr']:.0f}%",
        "",
        "## Naive wash-day baselines (same universe, CF rows)",
        "",
        "| baseline | tune n/net/WR | holdout n/net/WR |",
        "|----------|---------------|------------------|",
    ]
    for name in ("always_p0_sealed", "always_ft_dl", "oracle_best_row"):
        t = baselines[f"{name}_tune"]
        h = baselines[f"{name}_holdout"]
        md.append(
            f"| {name} | {t['n']} / {t['net']:+.0f} / {t['wr']:.0f}% | "
            f"{h['n']} / {h['net']:+.0f} / {h['wr']:.0f}% |"
        )
    md.extend(
        [
            "",
            "## Top grid (score = tune_net + 0.5×hold_net − 2×|worst_tune_month|)",
            "",
            _markdown_table(results),
            "",
            f"Full JSON: `{out_json.relative_to(root)}`",
        ]
    )
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(out_md.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
