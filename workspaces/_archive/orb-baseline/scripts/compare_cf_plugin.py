"""Compare FT-009 CF rm30_bk0p15 vs plugin baseline_0104."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "reports"
    cf = json.loads((root / "counterfactual_orb_0104.json").read_text(encoding="utf-8"))
    pl = json.loads((root / "baseline_0104.json").read_text(encoding="utf-8"))

    cf_trades = {t["day"]: t for t in cf["entries"]["rm30_bk0p15"]}
    plugin_days: dict[str, dict] = {}
    for d in pl["daily_summaries"]:
        perf = d.get("performance") or {}
        exp = perf.get("expectancy") or {}
        op = d.get("operational") or {}
        sig = d.get("signals") or {}
        plugin_days[d["date"]] = {
            "tc": int(exp.get("trade_count") or 0),
            "gross_total": float(perf.get("total_pnl_gross") or 0),
            "net_total": float(perf.get("total_pnl_net") or 0),
            "cancelled": int(op.get("intent_cancelled") or 0),
            "entries": int(sig.get("entry_signals") or 0),
        }

    cf_only: list[tuple] = []
    pl_only: list[tuple] = []
    both: list[tuple] = []
    for day in sorted(set(cf_trades) | set(plugin_days)):
        cf_t = cf_trades.get(day)
        pl_d = plugin_days.get(day, {})
        cf_has = cf_t is not None
        pl_has = pl_d.get("tc", 0) > 0
        if cf_has and not pl_has:
            cf_only.append((day, cf_t, pl_d))
        elif pl_has and not cf_has:
            pl_only.append((day, cf_t, pl_d))
        elif cf_has and pl_has:
            both.append((day, cf_t, pl_d))

    print("=== COUNTS ===")
    print(f"CF trades: {len(cf_trades)}")
    print(f"Plugin completed_rounds: {pl['completed_rounds']}")
    print(f"Plugin entry_signals: {pl['entry_signals']}")
    print(f"Plugin intent_cancelled: {pl['intent_cancelled']}")
    print()

    print("=== CF signal but NO plugin round ===")
    for day, cf_t, pl_d in cf_only:
        print(
            f"  {day} CF {cf_t['direction']} gross={cf_t['gross_atr_sim']:.2f} "
            f"entry={cf_t['entry_price']} atr={cf_t['atr']} "
            f"exit={cf_t['atr_barrier_sim']['exit_reason']} "
            f"| entries={pl_d.get('entries', 0)} cancelled={pl_d.get('cancelled', 0)}"
        )
    print()

    print("=== Plugin round but NO CF signal ===")
    for day, _cf_t, pl_d in pl_only:
        print(
            f"  {day} plugin gross={pl_d.get('gross_total')} net={pl_d.get('net_total')}"
        )
    print()

    print("=== BOTH traded — PnL delta (plugin_gross - CF_gross), worst first ===")
    deltas: list[tuple[float, str, dict, dict]] = []
    for day, cf_t, pl_d in both:
        cf_g = float(cf_t["gross_atr_sim"])
        pl_g = float(pl_d.get("gross_total") or 0)
        deltas.append((pl_g - cf_g, day, cf_t, pl_d))
    deltas.sort()
    for delta, day, cf_t, pl_d in deltas[:10]:
        cf_g = float(cf_t["gross_atr_sim"])
        print(
            f"  {day} delta={delta:+.1f} CF {cf_t['direction']} gross={cf_g:.1f} "
            f"exit={cf_t['atr_barrier_sim']['exit_reason']} "
            f"| plugin gross={pl_d.get('gross_total')}"
        )
    print("... best deltas:")
    for delta, day, cf_t, pl_d in deltas[-5:]:
        cf_g = float(cf_t["gross_atr_sim"])
        print(
            f"  {day} delta={delta:+.1f} CF {cf_t['direction']} gross={cf_g:.1f} "
            f"| plugin gross={pl_d.get('gross_total')}"
        )
    print()

    cf_gross = sum(t["gross_atr_sim"] for t in cf_trades.values())
    pl_gross = sum(d.get("gross_total", 0) for d in plugin_days.values())
    missed = sum(t["gross_atr_sim"] for _, t, _ in cf_only)
    matched_delta = sum(d for d, _, _, _ in deltas)
    print("=== TOTALS ===")
    print(f"CF gross total: {cf_gross:.1f}  mean={cf_gross/len(cf_trades):.2f}")
    print(f"Plugin gross total: {pl_gross:.1f}  mean={pl_gross/pl['completed_rounds']:.2f}")
    print(f"Gap: {pl_gross - cf_gross:.1f}")
    print(f"  from missed CF days: {-missed:.1f} (CF gross on days plugin skipped)")
    print(f"  from matched-day PnL drift: {matched_delta:.1f}")
    print(f"Avg delta on {len(deltas)} matched days: {matched_delta/len(deltas):.2f}")

    # Direction breakdown on matched
    by_dir: dict[str, list[float]] = {"Long": [], "Short": []}
    for _d, cf_t, pl_d in both:
        by_dir[cf_t["direction"]].append(
            float(pl_d.get("gross_total") or 0) - float(cf_t["gross_atr_sim"])
        )
    # Exit reason mix on matched days
    cf_exits: dict[str, int] = {}
    pl_exits: dict[str, int] = {}
    tp_miss = 0
    for day, cf_t, pl_d in both:
        cf_er = cf_t["atr_barrier_sim"]["exit_reason"]
        cf_exits[cf_er] = cf_exits.get(cf_er, 0) + 1
        # plugin exit from daily pnl by_reason
        by_reason = {}
        for d in pl["daily_summaries"]:
            if d["date"] == day:
                by_reason = (d.get("pnl") or {}).get("by_reason") or {}
                break
        if by_reason:
            pl_er = next(iter(by_reason))
            pl_exits[pl_er] = pl_exits.get(pl_er, 0) + 1
            if cf_er == "take_profit" and pl_er != "take_profit":
                tp_miss += 1

    print("=== Exit reason mix (matched days) ===")
    print(f"  CF: {cf_exits}")
    print(f"  Plugin: {pl_exits}")
    print(f"  CF take_profit but plugin not: {tp_miss} days")
    for direction, vals in by_dir.items():
        if vals:
            print(f"  {direction}: n={len(vals)} avg_delta={sum(vals)/len(vals):.2f}")


if __name__ == "__main__":
    main()
