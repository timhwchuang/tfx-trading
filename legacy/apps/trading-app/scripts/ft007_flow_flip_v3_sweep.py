"""FT-007 Phase 0 v3: sweep close_1h / footprint / flip-surge variants."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from reporting.flow_flip_counterfactual import (
    DEFAULT_FLIP_SURGE_MULT,
    build_flow_flip_payload,
)

PILOT_DATES = (
    "2026-01-15",
    "2026-02-20",
    "2026-03-12",
    "2026-04-08",
    "2026-04-22",
)

V3_VARIANTS: list[tuple[str, dict]] = [
    (
        "v3_close_1h",
        {"close_1h_only": True},
    ),
    (
        "v3_footprint",
        {"footprint_enabled": True},
    ),
    (
        "v3_flip_surge_1p5",
        {"flip_surge_mult": DEFAULT_FLIP_SURGE_MULT},
    ),
    (
        "v3_all",
        {
            "close_1h_only": True,
            "footprint_enabled": True,
            "flip_surge_mult": DEFAULT_FLIP_SURGE_MULT,
        },
    ),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact_summary(payload: dict) -> dict:
    overall = _summarize_rows(payload.get("entries") or [])
    by_setup = payload.get("summary_by_setup_side") or {}
    return {
        "variant": payload.get("variant"),
        "entry_count": payload.get("entry_count"),
        "phase0_pass": (payload.get("phase0_gate") or {}).get("pass"),
        "best_passing": (payload.get("phase0_gate") or {}).get("best_passing"),
        "flow_diagnostics": (payload.get("flow_diagnostics") or {}).get("totals"),
        "overall": overall,
        "by_setup_side": {
            side: (block.get("scalp") or {})
            for side, block in by_setup.items()
        },
    }


def _summarize_rows(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "gross_mean": None, "net_mean": None}
    n = len(rows)
    gross = sum(r["gross_scalp"] for r in rows) / n
    net = sum(r["net_scalp"] for r in rows) / n
    return {"n": n, "gross_mean": round(gross, 2), "net_mean": round(net, 2)}


def _write_gate_report(path: Path, summaries: list[dict], baseline: dict) -> None:
    lines = [
        "# FT-007 Gate Report — mer-baseline（Phase 0 v3 sweep）",
        "",
        f"**Baseline v2**：n={baseline.get('entry_count')} gross={baseline.get('overall', {}).get('gross_mean')} net={baseline.get('overall', {}).get('net_mean')}",
        "",
        "## v3 對照（pilot 5 日）",
        "",
        "| variant | n | gross/趟 | net/趟 | phase0 | best |",
        "|---------|---|----------|--------|--------|------|",
    ]
    for s in summaries:
        o = s.get("overall") or {}
        best = s.get("best_passing")
        best_s = (
            f"{best.get('setup_side')}×{best.get('session_bucket')} n={best.get('n')}"
            if best
            else "—"
        )
        lines.append(
            f"| {s.get('variant')} | {o.get('n', '—')} | {o.get('gross_mean', '—')} | "
            f"{o.get('net_mean', '—')} | {s.get('phase0_pass')} | {best_s} |"
        )
    lines.extend(
        [
            "",
            "產物：[`reports/counterfactual_flow_flip_v3_sweep.json`](reports/counterfactual_flow_flip_v3_sweep.json)",
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )
    any_pass = any(s.get("phase0_pass") for s in summaries)
    if any_pass:
        lines.append("| 決策 | **某 v3 子集過 Phase 0** — 見上表 best |")
    else:
        lines.append("| 決策 | **v3 全未過 Phase 0** — Thesis D 維持 No-Go |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "mer-baseline"
    parser = argparse.ArgumentParser(description="FT-007 flow flip v3 sweep")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument(
        "--output",
        type=Path,
        default=ws / "reports" / "counterfactual_flow_flip_v3_sweep.json",
    )
    parser.add_argument("--gate-report", type=Path, default=ws / "gate_report.md")
    args = parser.parse_args(argv)

    dates = [dt.date.fromisoformat(d) for d in PILOT_DATES]
    baseline_payload = build_flow_flip_payload(
        code=args.code,
        cache_dir=args.cache_dir,
        dates=dates,
        variant="v2_baseline",
    )
    results: list[dict] = []
    summaries: list[dict] = []
    baseline_summary = _compact_summary(baseline_payload)
    summaries.append(baseline_summary)

    for name, kwargs in V3_VARIANTS:
        payload = build_flow_flip_payload(
            code=args.code,
            cache_dir=args.cache_dir,
            dates=dates,
            variant=name,
            **kwargs,
        )
        compact = _compact_summary(payload)
        summaries.append(compact)
        results.append(
            {
                "variant": name,
                "params": kwargs,
                "summary": compact,
                "phase0_gate": payload.get("phase0_gate"),
                "summary_by_setup_and_bucket": payload.get("summary_by_setup_and_bucket"),
                "entry_count": payload.get("entry_count"),
            }
        )

    out = {
        "pilot_dates": list(PILOT_DATES),
        "baseline": baseline_summary,
        "variants": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_gate_report(args.gate_report, summaries[1:], baseline_summary)

    for s in summaries:
        o = s.get("overall") or {}
        print(
            f"{s.get('variant')}: n={o.get('n')} gross={o.get('gross_mean')} "
            f"net={o.get('net_mean')} pass={s.get('phase0_pass')}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
