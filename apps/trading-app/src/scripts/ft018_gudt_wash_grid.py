"""FT-018b: GUDT wash grid v2 CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.gudt_wash_grid import build_gudt_wash_grid_payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _payload_for_json(payload: dict) -> dict:
    out = dict(payload)
    out.pop("rows_by_param", None)
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    reports = root / "workspaces" / "gudt-baseline" / "reports"
    parser = argparse.ArgumentParser(description="FT-018b GUDT wash grid v2")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from", dest="from_date", default="2025-12-01")
    parser.add_argument("--to", dest="to_date", default="2026-05-31")
    parser.add_argument("--grid", action="store_true", required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--compare-baseline",
        type=Path,
        default=None,
        help="Optional sealed baseline JSON for side-by-side summary",
    )
    args = parser.parse_args(argv)

    payload = build_gudt_wash_grid_payload(
        code=args.code,
        from_date=args.from_date,
        to_date=args.to_date,
        cache_dir=args.cache_dir,
    )

    suffix = f"{args.from_date.replace('-', '')}_{args.to_date.replace('-', '')}"
    out = args.out or reports / f"counterfactual_gudt_wash_grid_{suffix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_payload_for_json(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    compare_lines: list[str] = []
    if args.compare_baseline and args.compare_baseline.is_file():
        baseline = json.loads(args.compare_baseline.read_text(encoding="utf-8"))
        sealed_best = (baseline.get("phase0_gate") or {}).get("best_passing") or {}
        sealed_net = None
        if sealed_best.get("param"):
            s = (baseline.get("summary_by_param") or {}).get(sealed_best["param"], {})
            block = (s or {}).get("atr_trail_skew_900s") or s
            if block:
                sealed_net = block.get("net_total") or (
                    float(block.get("net_mean", 0)) * int(block.get("n", 0))
                )
        compare_lines = [
            "",
            "## Baseline comparison",
            f"- sealed best: {sealed_best.get('param')} net≈{sealed_net}",
            f"- wash grid best: {payload.get('best_param')} net={payload.get('best_net_total')}",
        ]

    summary_path = out.with_suffix(".compare.md")
    summary_path.write_text(
        "\n".join(
            [
                "# GUDT Wash Grid vs Sealed Baseline",
                "",
                f"- range: {args.from_date} ~ {args.to_date}",
                f"- wash best: `{payload.get('best_param')}` net_total={payload.get('best_net_total')}",
                f"- params swept: {payload.get('param_count')}",
                *compare_lines,
                "",
                f"Full JSON: `{out.name}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"wash grid best={payload.get('best_param')} net={payload.get('best_net_total')} -> {out}",
        flush=True,
    )
    print(f"compare: {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
