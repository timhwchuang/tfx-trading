"""FT-008 Phase 0: short breakout counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.short_breakout_counterfactual import build_short_breakout_payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _write_gate_report(path: Path, payload: dict) -> None:
    gate = payload["phase0_gate"]
    ref = payload.get("ft004_baseline_reference") or {}
    lines = [
        "# FT-008 Gate Report — sb-baseline（Phase 0）",
        "",
        f"> **狀態：{'Go Phase 1' if gate['pass'] else 'MVPClosed / No-Go at Phase 0'}** — 見 "
        f"[`SPEC`](../../docs/features/short-breakout/SPEC.md)。",
        "",
        f"**區間**：{payload['from_date']} ～ {payload['to_date']}",
        f"**產物**：[`reports/counterfactual_short_breakout.json`](reports/counterfactual_short_breakout.json)",
        "",
        "## Phase 0 預檢",
        "",
        f"| 通過 | {gate['pass']} |",
        f"| gross_mean 門檻 | > {gate['gross_mean_min']} |",
        f"| net_mean 門檻 | > {gate['net_mean_min']} |",
        f"| min_n | {gate['min_n']} |",
        "",
        f"**FT-004 對照**（armed 全進 valid）：gross ~ **{ref.get('gross_mean_per_trade', '—')}**/趟（G1 未過）",
        "",
    ]
    best = gate.get("best_passing")
    if best:
        lines.extend(
            [
                "### Best passing (param × bucket)",
                "",
                f"- param={best['param']} bucket={best['session_bucket']}",
                f"- n={best['n']} gross_mean={best['gross_mean']} net_mean={best['net_mean']}",
                "",
            ]
        )
    else:
        lines.append("**無任一組通過 Phase 0 門檻。**\n")

    lines.extend(
        [
            "## summary_by_param（atr_barrier_180s）",
            "",
            "| param | n | gross/趟 | net/趟 |",
            "|---|---|----------|--------|",
        ]
    )
    for param, block in sorted(payload.get("summary_by_param", {}).items()):
        s = block.get("atr_barrier_180s") or {}
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    lines.extend(
        [
            "",
            "## summary_by_param（fixed_scalp_120s）",
            "",
            "| param | n | gross/趟 | net/趟 |",
            "|---|---|----------|--------|",
        ]
    )
    for param, block in sorted(payload.get("summary_by_param", {}).items()):
        s = block.get("fixed_scalp_120s") or {}
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    lines.extend(["", "## §Decision", "", "| 欄位 | 值 |", "|------|-----|"])
    if gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — 開 plugin + baseline |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_e_phase0_no_go`) |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "sb-baseline"
    parser = argparse.ArgumentParser(description="FT-008 short breakout counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--lookback", type=int, nargs="*", default=[5, 10, 15])
    parser.add_argument("--breakout-atr-k", type=float, nargs="*", default=[0.0, 0.1])
    parser.add_argument("--vol-pct", type=float, default=70.0)
    parser.add_argument("--min-range-atr-k", type=float, default=0.5)
    parser.add_argument("--skip-open-min", type=int, default=10)
    parser.add_argument("--cooldown-sec", type=int, default=120)
    parser.add_argument("--hard-stop-atr-k", type=float, default=0.75)
    parser.add_argument("--tp-atr-k", type=float, default=2.0)
    parser.add_argument("--sl-points", type=float, default=8.0)
    parser.add_argument("--tp-points", type=float, default=12.0)
    parser.add_argument("--horizon-seconds", type=int, default=1800)
    parser.add_argument("--close-1h-only", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ws / "reports" / "counterfactual_short_breakout.json",
    )
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=ws / "gate_report.md",
    )
    args = parser.parse_args(argv)

    payload = build_short_breakout_payload(
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        lookback_bars=tuple(args.lookback),
        breakout_atr_ks=tuple(args.breakout_atr_k),
        vol_pct=args.vol_pct,
        min_range_atr_k=args.min_range_atr_k,
        skip_open_min=args.skip_open_min,
        cooldown_sec=args.cooldown_sec,
        hard_stop_atr_k=args.hard_stop_atr_k,
        tp_atr_k=args.tp_atr_k,
        sl_points=args.sl_points,
        tp_points=args.tp_points,
        horizon_seconds=args.horizon_seconds,
        close_1h_only=args.close_1h_only,
        variant="v2_close_1h_only" if args.close_1h_only else "v1_baseline",
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_gate_report(args.gate_report, payload)

    gate = payload["phase0_gate"]
    print(
        f"Wrote {args.output} | phase0_pass={gate['pass']} best={gate.get('best_passing')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
