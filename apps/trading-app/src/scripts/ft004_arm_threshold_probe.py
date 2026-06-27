"""FT-004 No-Go arm tuning: counterfactual grid over vol / buy / sell thresholds."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from reporting.armed_forward_counterfactual import (
    build_counterfactual_payload_from_rows,
    prepare_counterfactual_episodes,
)
from reporting.uat_report import read_log_lines


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _score_row(row: dict) -> float:
    """Prefer positive gross edge; penalize high n (G3) and negative net."""
    s = row["summary"]["atr_barrier_180s"]
    gross = s.get("gross_mean")
    net = s.get("net_mean")
    n = s.get("n") or 0
    if gross is None:
        return -1e9
    score = float(gross)
    if net is not None and net > 0:
        score += 2.0
    if n > 100:
        score -= (n - 100) * 0.05
    return score


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="FT-004 arm threshold counterfactual probe")
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
        "--vol-grid",
        nargs="+",
        type=float,
        default=[150, 165, 180, 195, 210],
    )
    parser.add_argument(
        "--buy-grid",
        nargs="+",
        type=float,
        default=[0.80, 0.85, 0.90],
    )
    parser.add_argument(
        "--sell-grid",
        nargs="+",
        type=float,
        default=[0.78, 0.83, 0.88],
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "workspaces" / "mc-baseline" / "reports" / "arm_threshold_probe.json",
    )
    args = parser.parse_args(argv)

    if not args.log.is_file():
        raise SystemExit(f"log not found: {args.log}")

    lines = read_log_lines([args.log])
    per_episode_all, _outcomes, armed_total = prepare_counterfactual_episodes(
        log_lines=lines,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
    )

    rows: list[dict] = []
    for vol, buy, sell in itertools.product(args.vol_grid, args.buy_grid, args.sell_grid):
        payload = build_counterfactual_payload_from_rows(
            per_episode_all=per_episode_all,
            armed_total=armed_total,
            from_date=args.from_date,
            to_date=args.to_date,
            code=args.code,
            min_vol_1s=vol,
            min_buy_ratio=buy,
            min_sell_ratio=sell,
        )
        s = payload["summary_all"]["atr_barrier_180s"]
        filt = payload["arm_filter"]
        rows.append(
            {
                "momentum_vol_1s": vol,
                "momentum_buy_ratio": buy,
                "momentum_sell_ratio": sell,
                "armed_before": filt["armed_before_filter"],
                "armed_after": filt["armed_after_filter"],
                "summary": payload["summary_all"],
                "timeout_atr_gross_mean": (
                    payload.get("summary_by_outcome_v1", {})
                    .get("timeout", {})
                    .get("atr_barrier_180s", {})
                    .get("gross_mean")
                ),
                "entered_atr_gross_mean": (
                    payload.get("summary_by_outcome_v1", {})
                    .get("entered", {})
                    .get("atr_barrier_180s", {})
                    .get("gross_mean")
                ),
            }
        )

    rows.sort(key=_score_row, reverse=True)
    best = rows[0] if rows else None

    out = {
        "schema_version": 1,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "grid": {
            "vol": args.vol_grid,
            "buy_ratio": args.buy_grid,
            "sell_ratio": args.sell_grid,
        },
        "ranked": rows,
        "recommended": best,
    }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if best:
        s = best["summary"]["atr_barrier_180s"]
        print(
            f"Wrote {args.json_out} | best vol={best['momentum_vol_1s']} "
            f"buy={best['momentum_buy_ratio']} sell={best['momentum_sell_ratio']} "
            f"n={s.get('n')} gross_mean={s.get('gross_mean')} net_mean={s.get('net_mean')}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
