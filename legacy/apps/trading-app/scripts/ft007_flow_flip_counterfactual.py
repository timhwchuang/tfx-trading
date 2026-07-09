"""FT-007 Phase 0 v2: tick flow flip counterfactual CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reporting.flow_flip_counterfactual import build_flow_flip_payload

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
    diag = payload.get("flow_diagnostics", {}).get("totals", {})
    lines = [
        "# FT-007 Gate Report — mer-baseline（Phase 0 v2 · flow flip）",
        "",
        f"> **狀態：{'Go Phase 1' if gate['pass'] else 'No-Go at Phase 0 v2'}**",
        "",
        f"**Pilot 日**：{', '.join(payload.get('dates', []))}",
        "**產物**：[`reports/counterfactual_flow_flip_pilot.json`](reports/counterfactual_flow_flip_pilot.json)",
        "",
        "## Flow 診斷（事件數，非成交）",
        "",
        f"| buy_setups | {diag.get('buy_setups', '—')} |",
        f"| sell_setups | {diag.get('sell_setups', '—')} |",
        f"| buy_flips (空) | {diag.get('buy_flips', '—')} |",
        f"| sell_flips (多) | {diag.get('sell_flips', '—')} |",
        f"| **entries** | **{payload.get('entry_count', 0)}** |",
        "",
        "## Phase 0 預檢（scalp sim）",
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
                "### Best passing",
                "",
                f"- setup={best['setup_side']} bucket={best['session_bucket']}",
                f"- n={best['n']} gross_mean={best['gross_mean']} net_mean={best['net_mean']}",
                "",
            ]
        )

    lines.extend(
        [
            "## summary_by_setup_side",
            "",
            "| setup | n | gross/趟 | net/趟 |",
            "|-------|---|----------|--------|",
        ]
    )
    for side, block in payload.get("summary_by_setup_side", {}).items():
        s = block.get("scalp") or {}
        lines.append(
            f"| {side} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    lines.extend(["", "## §Decision", "", "| 欄位 | 值 |", "|------|-----|"])
    if gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — flow v2 過關 |")
    else:
        lines.append("| 決策 | **No-Go Phase 0 v2** |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "mer-baseline"
    parser = argparse.ArgumentParser(description="FT-007 flow flip counterfactual v2")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--setup-side-ratio", type=float, default=0.62)
    parser.add_argument("--setup-sustain-sec", type=int, default=40)
    parser.add_argument(
        "--output",
        type=Path,
        default=ws / "reports" / "counterfactual_flow_flip_pilot.json",
    )
    parser.add_argument("--gate-report", type=Path, default=ws / "gate_report.md")
    args = parser.parse_args(argv)

    if args.pilot:
        dates = [dt.date.fromisoformat(d) for d in PILOT_DATES]
        payload = build_flow_flip_payload(
            code=args.code,
            cache_dir=args.cache_dir,
            dates=dates,
            setup_side_ratio=args.setup_side_ratio,
            setup_sustain_sec=args.setup_sustain_sec,
        )
    else:
        if not args.from_date or not args.to_date:
            raise SystemExit("provide --pilot or --from-date/--to-date")
        payload = build_flow_flip_payload(
            code=args.code,
            cache_dir=args.cache_dir,
            from_date=args.from_date,
            to_date=args.to_date,
            setup_side_ratio=args.setup_side_ratio,
            setup_sustain_sec=args.setup_sustain_sec,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_gate_report(args.gate_report, payload)

    gate = payload["phase0_gate"]
    diag = payload.get("flow_diagnostics", {}).get("totals", {})
    print(
        f"Wrote {args.output} | entries={payload.get('entry_count')} "
        f"diag={diag} phase0_pass={gate['pass']} best={gate.get('best_passing')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
