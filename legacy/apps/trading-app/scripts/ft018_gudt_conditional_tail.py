"""FT-018b: conditional p0 tail exit — momentum_clean / ext_open gates."""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS
from reporting.gudt_wash_probe import (
    BPrimeCompositeParams,
    DayWashContext,
    ProbeEntry,
    ext_open_atr,
    load_probe_contexts,
    read_probe_csv,
    summarize_b_prime_composite,
    _probe_entry_from_row,
    _row_for,
    _simulate_exit,
)
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit

GateMode = Literal["clean", "ext", "clean_and_ext", "clean_or_ext"]


@dataclass(frozen=True)
class TailExitParams:
    max_hold_sec: int = 1800
    trail_dist_atr_k: float = 1.0
    trail_arm_atr_k: float = 2.0
    be_trigger_atr_k: float = 0.75
    hard_stop_atr_k: float = 1.25
    ext_open_min: float = 5.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _tail_sim(entry: ProbeEntry, ctx: DayWashContext, tail: TailExitParams) -> dict[str, Any]:
    return simulate_atr_trail_skew_exit(
        direction="Long",
        entry_price=entry.entry_price,
        entry_ts=entry.entry_ts,
        atr=ctx.atr,
        ticks=ctx.ticks,
        hard_stop_atr_k=tail.hard_stop_atr_k,
        be_trigger_atr_k=tail.be_trigger_atr_k,
        trail_arm_atr_k=tail.trail_arm_atr_k,
        trail_dist_atr_k=tail.trail_dist_atr_k,
        hard_tp_atr_k=None,
        max_hold_sec=tail.max_hold_sec,
    )


def _gate_ok(
    *,
    wash_label: str,
    ext: float,
    mode: GateMode,
    ext_open_min: float,
) -> bool:
    clean = wash_label == "momentum_clean"
    ext_hi = ext > ext_open_min
    if mode == "clean":
        return clean
    if mode == "ext":
        return ext_hi
    if mode == "clean_and_ext":
        return clean and ext_hi
    return clean or ext_hi


def summarize_conditional_tail(
    picks: list[dict[str, Any]],
    *,
    by_day: dict[str, list[dict[str, Any]]],
    ctx_by_day: dict[str, DayWashContext],
    mode: GateMode | None,
    tail: TailExitParams,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any]:
    """Re-sim p0 exits; ``mode=None`` = baseline sealed. ft picks unchanged."""
    out: list[dict[str, Any]] = []
    tail_days = 0
    for p in picks:
        day = p["day"]
        ctx = ctx_by_day.get(day)
        base_net = float(p["net"])
        if ctx is None or not p["path"].startswith("p0"):
            out.append({**p, "exit_mode": "ft_dl", "tail_gate": False})
            continue
        row = _row_for(by_day[day], "p0", "sealed")
        if row is None:
            out.append({**p, "exit_mode": "sealed", "tail_gate": False})
            continue
        entry = _probe_entry_from_row(row)
        label = str(row.get("wash_label") or "")
        ext = ext_open_atr(ctx)
        use_tail = mode is not None and _gate_ok(
            wash_label=label, ext=ext, mode=mode, ext_open_min=tail.ext_open_min
        )
        if use_tail:
            sim = _tail_sim(entry, ctx, tail)
            net = round(float(sim["gross_pnl"]) - friction, 2)
            tail_days += 1
            out.append({
                **p,
                "net": net,
                "exit_mode": "tail30m",
                "tail_gate": True,
                "wash_label": label,
                "ext_open": round(ext, 2),
                "exit_reason": sim["exit_reason"],
                "hold_sec": sim["hold_sec"],
            })
        else:
            sim = _simulate_exit(entry, ctx, "sealed")
            net = round(float(sim["gross_pnl"]) - friction, 2)
            out.append({
                **p,
                "net": net,
                "exit_mode": "sealed",
                "tail_gate": False,
                "wash_label": label,
                "ext_open": round(ext, 2),
                "exit_reason": sim["exit_reason"],
                "hold_sec": sim.get("hold_sec"),
            })
    nets = [float(x["net"]) for x in out]
    caps = []
    for x in out:
        if float(x["net"]) <= 0 or not x["path"].startswith("p0"):
            continue
        row = _row_for(by_day[x["day"]], "p0", "sealed")
        if row and float(row["mfe"]) > 0:
            caps.append(float(x["net"]) / float(row["mfe"]))
    return {
        "mode": mode or "baseline",
        "n": len(out),
        "tail_days": tail_days,
        "net_total": round(sum(nets), 2),
        "net_mean": round(statistics.mean(nets), 2) if nets else 0.0,
        "win_rate": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1) if nets else 0.0,
        "worst": round(min(nets), 2) if nets else 0.0,
        "capture": round(statistics.mean(caps), 3) if caps else 0.0,
        "picks": out,
    }


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b conditional tail exit counterfactual")
    parser.add_argument("--from", dest="from_date", default="2025-05-01")
    parser.add_argument("--to", dest="to_date", default="2026-06-30")
    parser.add_argument(
        "--from-csv",
        type=Path,
        default=reports / "gudt_wash_probe_merged_202505_202606.csv",
    )
    parser.add_argument("--ext-open-min", type=float, default=5.0)
    parser.add_argument("--out-md", type=Path, default=None)
    args = parser.parse_args(argv)

    rows = read_probe_csv(args.from_csv)
    rows = [r for r in rows if args.from_date <= r["day"] <= args.to_date]
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_day[r["day"]].append(r)
    ctx_by_day = load_probe_contexts(
        "TMFR1", sorted(by_day), cache_dir=root / "tick_cache"
    )
    br5 = BPrimeCompositeParams(
        pre_break_br_min=0.35, pre_break_br_p0_only=True, flip_min_ext_open=999.0
    )
    base_picks = summarize_b_prime_composite(
        rows, ctx_by_day=ctx_by_day, params=br5
    )["picks"]
    tail = TailExitParams(ext_open_min=args.ext_open_min)

    specs: list[tuple[str, GateMode | None]] = [
        ("baseline sealed", None),
        ("momentum_clean → tail30m", "clean"),
        (f"ext_open>{args.ext_open_min} → tail30m", "ext"),
        ("clean AND ext → tail30m", "clean_and_ext"),
        ("clean OR ext → tail30m", "clean_or_ext"),
    ]
    results = [
        summarize_conditional_tail(
            base_picks, by_day=by_day, ctx_by_day=ctx_by_day, mode=m, tail=tail
        )
        for _, m in specs
    ]
    base_net = results[0]["net_total"]

    lines = [
        "# GUDT conditional tail exit (B′ + br5-only picks)",
        "",
        f"Period: {args.from_date} .. {args.to_date}",
        "",
        "Tail leg (p0 only): no hard TP, hold 30m, trail_dist=1.0×ATR, BE=0.75.",
        "ft path: unchanged drive_low_struct.",
        "",
        "| spec | tail days | net | Δ | WR% | worst | capture |",
        "|------|----------:|----:|--:|----:|------:|--------:|",
    ]
    for r in results:
        d = round(r["net_total"] - base_net, 1)
        lines.append(
            f"| {r['mode']} | {r['tail_days']} | {r['net_total']:+.1f} | {d:+.1f} | "
            f"{r['win_rate']:.1f} | {r['worst']:+.1f} | {r['capture']:.0%} |"
        )

    best = max(results[1:], key=lambda r: r["net_total"])
    lines.extend(["", f"**Best gated:** `{best['mode']}` → net {best['net_total']:+.1f}"])
    if best["tail_days"]:
        lines.extend(["", "## Tail-trigger days (best spec)", ""])
        base_by = {p["day"]: p for p in results[0]["picks"]}
        for p in best["picks"]:
            if not p.get("tail_gate"):
                continue
            b = base_by.get(p["day"], {})
            delta = round(float(p["net"]) - float(b.get("net", 0)), 1)
            lines.append(
                f"- {p['day']}: ext={p.get('ext_open')} "
                f"base={float(b.get('net', 0)):+.0f} → tail={float(p['net']):+.0f} ({delta:+.0f}) "
                f"[{p.get('wash_label')}] {p.get('exit_reason')}"
            )

    out = args.out_md or reports / f"gudt_conditional_tail_{args.from_date}_{args.to_date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"baseline: net={base_net:+.1f}")
    for r in results[1:]:
        print(
            f"  {r['mode']}: tail={r['tail_days']} net={r['net_total']:+.1f} "
            f"d={r['net_total']-base_net:+.1f} worst={r['worst']:+.1f}"
        )
    print(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
