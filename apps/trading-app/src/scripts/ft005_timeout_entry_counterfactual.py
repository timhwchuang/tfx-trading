"""FT-005 Phase 0: timeout-selective entry counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.timeout_entry_counterfactual import build_timeout_counterfactual_payload
from reporting.uat_report import read_log_lines


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="FT-005 counterfactual: timeout-selective entry timings"
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
    parser.add_argument("--entry-band-points", type=float, default=2.0)
    parser.add_argument("--momentum-timeout-sec", type=int, default=180)
    parser.add_argument(
        "--output",
        "--json-out",
        dest="json_out",
        type=Path,
        default=root / "workspaces" / "tc-baseline" / "reports" / "counterfactual_timeout_entry.json",
    )
    args = parser.parse_args(argv)

    if not args.log.is_file():
        raise SystemExit(f"log not found: {args.log}")

    lines = read_log_lines([args.log])
    payload = build_timeout_counterfactual_payload(
        log_lines=lines,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        hard_stop_atr_k=args.hard_stop_atr_k,
        tp_atr_k=args.tp_atr_k,
        entry_band_points=args.entry_band_points,
        momentum_timeout_sec=args.momentum_timeout_sec,
    )

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    gate = payload["phase0_gate"]
    s = gate["timeout_tick_summary"]
    print(
        f"Wrote {args.json_out} | phase0_pass={gate['pass']} "
        f"timeout_tick gross_mean={s.get('gross_mean')} net_mean={s.get('net_mean')} n={s.get('n')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
