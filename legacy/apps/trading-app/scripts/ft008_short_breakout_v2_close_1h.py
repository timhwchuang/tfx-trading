"""FT-008 Phase 0 v2: close_1h_only short breakout counterfactual."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.short_breakout_counterfactual import build_short_breakout_payload


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
        "summary_by_direction": {
            k: {
                d: (block.get("atr_barrier_180s") or {})
                for d, block in dirs.items()
            }
            for k, dirs in (payload.get("summary_by_direction") or {}).items()
        },
        "entry_count_by_param": payload.get("entry_count_by_param"),
    }


def _write_gate_report(
    path: Path,
    *,
    valid: dict,
    aggregate: dict,
    valid_payload: dict,
    aggregate_payload: dict,
) -> None:
    v_gate = valid_payload["phase0_gate"]
    a_gate = aggregate_payload["phase0_gate"]
    lines = [
        "# FT-008 Gate Report — sb-baseline（Phase 0 v2 close_1h_only）",
        "",
        "> **Variant**：`v2_close_1h_only` — 僅收盤前 1h（12:45–13:45）1m 突破順勢。",
        "",
        "| 區間 | 產物 | Phase 0 |",
        "|------|------|---------|",
        f"| Valid {valid['from_date']}～{valid['to_date']} | "
        f"[`counterfactual_v2_close_1h_valid.json`](reports/counterfactual_v2_close_1h_valid.json) | "
        f"**{'通過' if v_gate['pass'] else '未過'}** |",
        f"| 01–04 {aggregate['from_date']}～{aggregate['to_date']} | "
        f"[`counterfactual_v2_close_1h_0104.json`](reports/counterfactual_v2_close_1h_0104.json) | "
        f"**{'通過' if a_gate['pass'] else '未過'}** |",
        "",
        "## Valid — summary_by_param（atr_barrier_180s）",
        "",
        "| param | n | gross/趟 | net/趟 |",
        "|---|---|----------|--------|",
    ]
    for param, s in sorted(valid.get("summary_by_param", {}).items()):
        if not s:
            continue
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    best_v = v_gate.get("best_passing")
    lines.extend(["", "### Best passing (valid)", ""])
    if best_v:
        lines.append(
            f"- {best_v['param']}: n={best_v['n']} gross={best_v['gross_mean']} net={best_v['net_mean']}"
        )
    else:
        lines.append("**無通過組。**")

    lines.extend(
        [
            "",
            "## 01–04 — summary_by_param（atr_barrier_180s）",
            "",
            "| param | n | gross/趟 | net/趟 |",
            "|---|---|----------|--------|",
        ]
    )
    for param, s in sorted(aggregate.get("summary_by_param", {}).items()):
        if not s:
            continue
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    best_a = a_gate.get("best_passing")
    lines.extend(["", "### Best passing (01–04)", ""])
    if best_a:
        lines.append(
            f"- {best_a['param']}: n={best_a['n']} gross={best_a['gross_mean']} net={best_a['net_mean']}"
        )
    else:
        lines.append("**無通過組。**")

    lines.extend(
        [
            "",
            "## v1 對照",
            "",
            "| 版本 | valid 最佳 | 01–04 最佳 |",
            "|------|-----------|------------|",
            "| v1 全時段（子集） | close_1h lb10_bk0.1 gross +7.24 | close_1h gross +4.40 |",
            f"| **v2 close_1h_only** | "
            f"{best_v['gross_mean'] if best_v else '—'} | "
            f"{best_a['gross_mean'] if best_a else '—'} |",
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )
    if v_gate["pass"] and a_gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — close_1h breakout plugin |")
    elif v_gate["pass"] and not a_gate["pass"]:
        lines.append("| 決策 | **Hold** — valid 過、01–04 未過（overfit 風險）；不開 plugin |")
    else:
        lines.append("| 決策 | **No-Go** (`thesis_e_v2_close_1h_no_go`) |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "sb-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-008 v2 close_1h_only counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--valid-from", default="2026-04-01")
    parser.add_argument("--valid-to", default="2026-04-30")
    parser.add_argument("--aggregate-from", default="2026-01-01")
    parser.add_argument("--aggregate-to", default="2026-04-30")
    parser.add_argument("--lookback", type=int, nargs="*", default=[5, 10, 15])
    parser.add_argument("--breakout-atr-k", type=float, nargs="*", default=[0.0, 0.1])
    args = parser.parse_args(argv)

    common = dict(
        code=args.code,
        cache_dir=args.cache_dir,
        lookback_bars=tuple(args.lookback),
        breakout_atr_ks=tuple(args.breakout_atr_k),
        close_1h_only=True,
        variant="v2_close_1h_only",
    )

    valid_payload = build_short_breakout_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )
    aggregate_payload = build_short_breakout_payload(
        from_date=args.aggregate_from,
        to_date=args.aggregate_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    valid_path = reports / "counterfactual_v2_close_1h_valid.json"
    aggregate_path = reports / "counterfactual_v2_close_1h_0104.json"
    valid_path.write_text(json.dumps(valid_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    aggregate_path.write_text(
        json.dumps(aggregate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    valid_compact = _compact(valid_payload)
    aggregate_compact = _compact(aggregate_payload)
    sweep_path = reports / "counterfactual_v2_close_1h_sweep.json"
    sweep_path.write_text(
        json.dumps(
            {"valid": valid_compact, "aggregate_0104": aggregate_compact},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    gate_path = ws / "gate_report_v2.md"
    _write_gate_report(
        gate_path,
        valid=valid_compact,
        aggregate=aggregate_compact,
        valid_payload=valid_payload,
        aggregate_payload=aggregate_payload,
    )

    print(
        f"Wrote {valid_path} valid_pass={valid_payload['phase0_gate']['pass']}",
        flush=True,
    )
    print(
        f"Wrote {aggregate_path} aggregate_pass={aggregate_payload['phase0_gate']['pass']}",
        flush=True,
    )
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
