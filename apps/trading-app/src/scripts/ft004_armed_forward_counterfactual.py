"""FT-004 Phase 0: armed-forward counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.armed_forward_counterfactual import build_counterfactual_payload
from reporting.uat_report import read_log_lines


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="FT-004 counterfactual: immediate entry on momentum_armed"
    )
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument(
        "--log",
        type=Path,
        default=root / "workspaces" / "agent-conservative" / "logs" / "baseline_valid.log",
    )
    parser.add_argument("--hard-stop-atr-k", type=float, default=0.75)
    parser.add_argument("--tp-atr-k", type=float, default=2.0)
    parser.add_argument("--min-vol-1s", type=float, default=None)
    parser.add_argument("--min-buy-ratio", type=float, default=None)
    parser.add_argument("--min-sell-ratio", type=float, default=None)
    parser.add_argument("--max-adverse-atr-k", type=float, default=None)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "workspaces" / "mc-baseline" / "reports" / "counterfactual_armed_forward.json",
    )
    args = parser.parse_args(argv)

    if not args.log.is_file():
        raise SystemExit(f"log not found: {args.log}")

    lines = read_log_lines([args.log])
    payload = build_counterfactual_payload(
        log_lines=lines,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        hard_stop_atr_k=args.hard_stop_atr_k,
        tp_atr_k=args.tp_atr_k,
        min_vol_1s=args.min_vol_1s,
        min_buy_ratio=args.min_buy_ratio,
        min_sell_ratio=args.min_sell_ratio,
        max_adverse_atr_k=args.max_adverse_atr_k,
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    s = payload["summary_all"]["atr_barrier_180s"]
    print(
        f"Wrote {args.json_out} | episodes={payload['episode_count']} "
        f"atr_sim net_mean={s.get('net_mean')} gross_mean={s.get('gross_mean')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
