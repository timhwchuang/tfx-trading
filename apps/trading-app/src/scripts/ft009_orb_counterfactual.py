"""FT-009 Phase 0: ORB counterfactual CLI (01-04 primary gate)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.orb_counterfactual import build_orb_payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact(payload: dict) -> dict:
    gate = payload.get("phase0_gate") or {}
    return {
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
        "variant": payload.get("variant"),
        "phase0_pass": gate.get("pass"),
        "best_passing": gate.get("best_passing"),
        "summary_by_param": {
            k: v.get("atr_barrier_180s")
            for k, v in (payload.get("summary_by_param") or {}).items()
        },
        "summary_by_direction": payload.get("summary_by_direction"),
        "days_with_valid_range": payload.get("days_with_valid_range"),
        "days_with_breakout": payload.get("days_with_breakout"),
        "entry_count_by_param": payload.get("entry_count_by_param"),
    }


def _write_gate_report(
    path: Path,
    *,
    aggregate: dict,
    valid: dict,
    aggregate_payload: dict,
    valid_payload: dict,
) -> None:
    a_gate = aggregate_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    lines = [
        "# FT-009 Gate Report — orb-baseline（Phase 0）",
        "",
        "> **Thesis F**：Opening Range Breakout — 開盤區間 first break only。",
        "> **主判**：**01–04 合計**（非 4 月單獨 tune）。",
        "",
        "| 區間 | 產物 | Phase 0 |",
        "|------|------|---------|",
        f"| **01–04** {aggregate['from_date']}～{aggregate['to_date']} | "
        f"[`counterfactual_orb_0104.json`](reports/counterfactual_orb_0104.json) | "
        f"**{'通過' if a_gate['pass'] else '未過'}** |",
        f"| Valid {valid['from_date']}～{valid['to_date']} | "
        f"[`counterfactual_orb_valid.json`](reports/counterfactual_orb_valid.json) | "
        f"{'通過' if v_gate['pass'] else '未過'}（參考） |",
        "",
        "## 01–04 主判 — summary_by_param",
        "",
        "| param | n | gross/趟 | net/趟 | break_days |",
        "|---|---|----------|--------|------------|",
    ]
    for param, s in sorted(aggregate.get("summary_by_param", {}).items()):
        if not s:
            continue
        breaks = (aggregate.get("days_with_breakout") or {}).get(param, "—")
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | "
            f"{s.get('net_mean', '—')} | {breaks} |"
        )

    best_a = a_gate.get("best_passing")
    lines.extend(["", "### Best passing（01–04）", ""])
    if best_a:
        lines.append(
            f"- {best_a['param']}: n={best_a['n']} gross={best_a['gross_mean']} net={best_a['net_mean']}"
        )
    else:
        lines.append("**無通過組。**")

    lines.extend(
        [
            "",
            "## Valid 2026-04（參考 only）",
            "",
            "| param | n | gross/趟 | net/趟 |",
            "|---|---|----------|--------|",
        ]
    )
    for param, s in sorted(valid.get("summary_by_param", {}).items()):
        if not s:
            continue
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    lines.extend(
        [
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )
    if a_gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — ORB plugin |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_f_orb_no_go`) |")
    if v_gate["pass"] and not a_gate["pass"]:
        lines.append("| 備註 | valid 過但 01–04 未過 — overfit suspect（同 FT-006/008） |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "orb-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-009 ORB counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--aggregate-from", default="2026-01-01")
    parser.add_argument("--aggregate-to", default="2026-04-30")
    parser.add_argument("--valid-from", default="2026-04-01")
    parser.add_argument("--valid-to", default="2026-04-30")
    parser.add_argument("--range-minutes", type=int, nargs="*", default=[15, 30])
    parser.add_argument("--buffer-atr-k", type=float, nargs="*", default=[0.0, 0.15])
    parser.add_argument("--min-range-atr-k", type=float, default=0.5)
    args = parser.parse_args(argv)

    common = dict(
        code=args.code,
        cache_dir=args.cache_dir,
        range_minutes=tuple(args.range_minutes),
        buffer_atr_ks=tuple(args.buffer_atr_k),
        min_range_atr_k=args.min_range_atr_k,
    )

    aggregate_payload = build_orb_payload(
        from_date=args.aggregate_from,
        to_date=args.aggregate_to,
        **common,
    )
    valid_payload = build_orb_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    aggregate_path = reports / "counterfactual_orb_0104.json"
    valid_path = reports / "counterfactual_orb_valid.json"
    aggregate_path.write_text(
        json.dumps(aggregate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(valid_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    aggregate_compact = _compact(aggregate_payload)
    valid_compact = _compact(valid_payload)
    sweep_path = reports / "counterfactual_orb_sweep.json"
    sweep_path.write_text(
        json.dumps(
            {"aggregate_0104": aggregate_compact, "valid_2026_04": valid_compact},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    gate_path = ws / "gate_report.md"
    _write_gate_report(
        gate_path,
        aggregate=aggregate_compact,
        valid=valid_compact,
        aggregate_payload=aggregate_payload,
        valid_payload=valid_payload,
    )

    a_gate = aggregate_payload["phase0_gate"]
    print(
        f"01-04 pass={a_gate['pass']} best={a_gate.get('best_passing')} -> {aggregate_path}",
        flush=True,
    )
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
