"""FT-004 §b: probe max_adverse_atr_k on r1b arm filters (counterfactual)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.armed_forward_counterfactual import (
    build_counterfactual_payload_from_rows,
    prepare_counterfactual_episodes,
)
from reporting.uat_report import read_log_lines

# r1b arm thresholds (fixed)
R1B_VOL = 165.0
R1B_BUY = 0.85
R1B_SELL = 0.78


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="FT-004 max_adverse_atr_k probe")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", default="2026-04-01")
    parser.add_argument("--to-date", default="2026-04-30")
    parser.add_argument(
        "--log",
        type=Path,
        default=root / "workspaces" / "agent-conservative" / "logs" / "baseline_valid.log",
    )
    parser.add_argument(
        "--k-grid",
        nargs="+",
        type=float,
        default=[0.0, 0.25, 0.5, 0.75, 1.0],
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "workspaces" / "mc-baseline" / "reports" / "adverse_guard_probe.json",
    )
    args = parser.parse_args(argv)

    lines = read_log_lines([args.log])
    per_episode_all, _, armed_total = prepare_counterfactual_episodes(
        log_lines=lines,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    rows: list[dict] = []
    for k in args.k_grid:
        payload = build_counterfactual_payload_from_rows(
            per_episode_all=per_episode_all,
            armed_total=armed_total,
            from_date=args.from_date,
            to_date=args.to_date,
            code=args.code,
            min_vol_1s=R1B_VOL,
            min_buy_ratio=R1B_BUY,
            min_sell_ratio=R1B_SELL,
            max_adverse_atr_k=k if k > 0 else None,
        )
        s = payload["summary_all"]["atr_barrier_180s"]
        rows.append(
            {
                "max_adverse_atr_k": k,
                "armed_after": payload["arm_filter"]["armed_after_filter"],
                "gross_mean": s.get("gross_mean"),
                "net_mean": s.get("net_mean"),
                "n": s.get("n"),
            }
        )

    rows.sort(key=lambda r: r.get("gross_mean") or -999, reverse=True)
    out = {"schema_version": 1, "r1b_arm": {"vol": R1B_VOL, "buy": R1B_BUY, "sell": R1B_SELL}, "ranked": rows, "recommended": rows[0]}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    best = rows[0]
    print(
        f"Wrote {args.json_out} | best k={best['max_adverse_atr_k']} "
        f"n={best['n']} gross={best['gross_mean']} net={best['net_mean']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
