"""FT-007 Phase 0: impulse exhaustion / absorption counterfactual CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reporting.impulse_absorption_counterfactual import build_impulse_absorption_payload

PILOT_DATES = (
    "2026-01-15",
    "2026-02-20",
    "2026-03-12",
    "2026-04-08",
    "2026-04-22",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _write_gate_report(path: Path, payload: dict) -> None:
    gate = payload["phase0_gate"]
    lines = [
        "# FT-007 Gate Report — mer-baseline（Phase 0 · pilot）",
        "",
        f"> **狀態：{'Go Phase 1' if gate['pass'] else 'MVPClosed / No-Go at Phase 0'}** — 見 "
        f"[`SPEC §8`](../../docs/features/momentum-exhaustion-reversal/SPEC.md)。",
        "",
        f"**Pilot 日**：{', '.join(payload.get('dates', []))}",
        "**產物**：[`reports/counterfactual_pilot.json`](reports/counterfactual_pilot.json)",
        "",
        "## Phase 0 預檢（pilot · scalp sim）",
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
                "### Best passing (impulse_bars × bucket)",
                "",
                f"- impulse_bars={best['impulse_bars']} bucket={best['session_bucket']}",
                f"- n={best['n']} gross_mean={best['gross_mean']} net_mean={best['net_mean']}",
                "",
            ]
        )
    else:
        lines.append("**無任一組通過 Phase 0 門檻。**\n")

    lines.extend(
        [
            "## summary_by_impulse_bars",
            "",
            "| bars | n | gross/趟 | net/趟 |",
            "|------|---|----------|--------|",
        ]
    )
    for bars_k, block in sorted(
        payload.get("summary_by_impulse_bars", {}).items(), key=lambda x: int(x[0])
    ):
        s = block.get("scalp") or {}
        lines.append(
            f"| {bars_k} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )
    lines.extend(["", "## §Decision", "", "| 欄位 | 值 |", "|------|-----|"])
    if gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — 開 plugin + baseline 01–04 |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_d_phase0_no_go`) |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "mer-baseline"
    parser = argparse.ArgumentParser(description="FT-007 impulse absorption counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--dates", nargs="*", default=None)
    parser.add_argument("--pilot", action="store_true", help="Use fixed 5-day pilot set")
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--impulse-bars", type=int, nargs="*", default=[3, 4])
    parser.add_argument("--tp-points", type=float, default=12.0)
    parser.add_argument("--sl-points", type=float, default=10.0)
    parser.add_argument("--max-hold-sec", type=int, default=120)
    parser.add_argument(
        "--output",
        type=Path,
        default=ws / "reports" / "counterfactual_pilot.json",
    )
    parser.add_argument("--gate-report", type=Path, default=ws / "gate_report.md")
    args = parser.parse_args(argv)

    if args.pilot:
        dates = [dt.date.fromisoformat(d) for d in PILOT_DATES]
        payload = build_impulse_absorption_payload(
            code=args.code,
            cache_dir=args.cache_dir,
            dates=dates,
            impulse_bars_list=tuple(args.impulse_bars),
            tp_points=args.tp_points,
            sl_points=args.sl_points,
            max_hold_sec=args.max_hold_sec,
        )
    else:
        if not args.from_date or not args.to_date:
            raise SystemExit("provide --pilot, or --from-date and --to-date")
        payload = build_impulse_absorption_payload(
            code=args.code,
            cache_dir=args.cache_dir,
            from_date=args.from_date,
            to_date=args.to_date,
            impulse_bars_list=tuple(args.impulse_bars),
            tp_points=args.tp_points,
            sl_points=args.sl_points,
            max_hold_sec=args.max_hold_sec,
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
