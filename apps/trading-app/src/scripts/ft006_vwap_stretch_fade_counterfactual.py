"""FT-006 Phase 0: VWAP stretch fade counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.vwap_stretch_fade_counterfactual import build_vwap_stretch_fade_payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _write_gate_report(
    path: Path,
    payload: dict,
) -> None:
    gate = payload["phase0_gate"]
    lines = [
        "# FT-006 Gate Report — vsf-baseline（Phase 0）",
        "",
        f"> **狀態：{'Go Phase 1' if gate['pass'] else 'MVPClosed / No-Go at Phase 0'}** — 見 "
        f"[`SPEC §8`](../../docs/features/vwap-stretch-fade/SPEC.md)。",
        "",
        f"**Valid**：{payload['from_date']} ～ {payload['to_date']}",
        f"**產物**：[`reports/counterfactual_vwap_stretch_fade.json`](reports/counterfactual_vwap_stretch_fade.json)",
        "",
        "## Phase 0 預檢",
        "",
        f"| 通過 | {gate['pass']} |",
        f"| gross_mean 門檻 | > {gate['gross_mean_min']} |",
        f"| net_mean 門檻 | > {gate['net_mean_min']} |",
        f"| min_n | {gate['min_n']} |",
        "",
    ]
    best = gate.get("best_passing")
    if best:
        lines.extend(
            [
                "### Best passing (k × bucket)",
                "",
                f"- stretch_k={best['stretch_k']} bucket={best['session_bucket']}",
                f"- n={best['n']} gross_mean={best['gross_mean']} net_mean={best['net_mean']}",
                "",
            ]
        )
    else:
        lines.append("**無任一組通過 Phase 0 門檻。**\n")

    lines.extend(["## summary_by_k（atr_barrier_180s）", "", "| k | n | gross/趟 | net/趟 |", "|---|---|----------|--------|"])
    for k, block in sorted(payload.get("summary_by_k", {}).items(), key=lambda x: float(x[0])):
        s = block.get("atr_barrier_180s") or {}
        lines.append(
            f"| {k} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )
    lines.extend(["", "## §Decision", "", "| 欄位 | 值 |", "|------|-----|"])
    if gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — 開 plugin + baseline |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_c_phase0_no_go`) |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "vsf-baseline"
    parser = argparse.ArgumentParser(description="FT-006 VWAP stretch fade counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--stretch-k", type=float, nargs="*", default=[1.5, 2.0, 2.5])
    parser.add_argument("--reset-z", type=float, default=0.5)
    parser.add_argument("--cooldown-sec", type=int, default=60)
    parser.add_argument("--hard-stop-atr-k", type=float, default=0.75)
    parser.add_argument("--tp-atr-k", type=float, default=2.0)
    parser.add_argument("--horizon-seconds", type=int, default=1800)
    parser.add_argument(
        "--output",
        type=Path,
        default=ws / "reports" / "counterfactual_vwap_stretch_fade.json",
    )
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=ws / "gate_report.md",
    )
    args = parser.parse_args(argv)

    payload = build_vwap_stretch_fade_payload(
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        stretch_ks=tuple(args.stretch_k),
        reset_z=args.reset_z,
        cooldown_sec=args.cooldown_sec,
        hard_stop_atr_k=args.hard_stop_atr_k,
        tp_atr_k=args.tp_atr_k,
        horizon_seconds=args.horizon_seconds,
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
