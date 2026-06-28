"""FT-013 Phase 0: SuperTrend flip counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.post_entry_diagnosis import format_gate_report_post_entry_section
from reporting.supertrend_flip_counterfactual import (
    EXIT_VARIANT,
    FINGERPRINT_ATR_PERIOD,
    FINGERPRINT_COOLDOWN_BARS,
    FINGERPRINT_K_SL,
    FINGERPRINT_ST_MULT,
    FINGERPRINT_TP_ATR_K,
    StfParams,
    build_stf_payload,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact(payload: dict) -> dict:
    gate = payload.get("phase0_gate") or {}
    fp = payload.get("fingerprint_gate")
    return {
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
        "variant": payload.get("variant"),
        "mode": payload.get("mode"),
        "phase0_pass": gate.get("pass"),
        "best_passing": gate.get("best_passing"),
        "fingerprint_pass": fp.get("pass") if fp else None,
        "summary_by_param": {
            k: v.get(EXIT_VARIANT) for k, v in (payload.get("summary_by_param") or {}).items()
        },
        "entry_count_by_param": payload.get("entry_count_by_param"),
        "funnel_by_param": payload.get("funnel_by_param"),
        "slippage_ratio_by_param": payload.get("slippage_ratio_by_param"),
    }


def _payload_for_json(payload: dict) -> dict:
    out = dict(payload)
    out.pop("rows_by_param", None)
    out.pop("short_appendix_rows_by_param", None)
    return out


def _write_gate_report(
    path: Path,
    *,
    train: dict,
    valid: dict,
    train_payload: dict,
    valid_payload: dict,
    mode: str,
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    fp_gate = train_payload.get("fingerprint_gate") or {}
    lines = [
        "# FT-013 Gate Report — stf-baseline（Phase 0）",
        "",
        "> **Thesis P-007**：SuperTrend flip continuation — long-only Phase 0。",
        "> **MUST-2**：FT-013 uses `entry_fill = entry_price + 1` before barrier — **gross 不可與 ORB/VSF raw entry 橫比**。",
        "",
        f"| 模式 | Train {train['from_date']}～{train['to_date']} | Valid {valid['from_date']}～{valid['to_date']} |",
        "|------|------|------|",
    ]
    if mode == "fingerprint":
        lines.append(
            f"| **Fingerprint (0c-1)** | "
            f"W30 med={fp_gate.get('w30_stop_less_gross_median', '—')} n={fp_gate.get('n', '—')} "
            f"**{'通過' if fp_gate.get('pass') else '未過'}** | （參考）valid |"
        )
    else:
        lines.append(
            f"| **Grid (0c-2)** | Phase0 **{'通過' if t_gate['pass'] else '未過'}** | "
            f"valid **{'通過' if v_gate['pass'] else '未過'}** |"
        )

    lines.extend(["", "## Train — summary_by_param", "", "| param | n | gross/趟 | net/趟 |", "|---|---:|---:|---:|"])
    for param, s in sorted(train.get("summary_by_param", {}).items()):
        if not s:
            continue
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
        )

    slip = train_payload.get("slippage_ratio_by_param") or {}
    if slip:
        lines.extend(["", "## Slippage ratio（MUST-2）", ""])
        for param, block in sorted(slip.items()):
            thin = " ⚠ execution_margin_thin" if block.get("execution_margin_thin") else ""
            lines.append(
                f"- `{param}`: p50={block.get('slippage_ratio_p50')} p90={block.get('slippage_ratio_p90')}{thin}"
            )

    funnel = train_payload.get("funnel_by_param") or {}
    if funnel:
        lines.extend(["", "## Funnel（MUST-3）", ""])
        for param, block in sorted(funnel.items()):
            totals = block.get("totals") or {}
            lines.append(
                f"- `{param}`: flip_long={totals.get('flip_detected_long')} → "
                f"cooldown={totals.get('cooldown_pass')} → window={totals.get('window_pass')} → "
                f"entry={totals.get('entry')}"
            )

    if mode == "fingerprint":
        lines.extend(["", "## Fingerprint (0c-1)", ""])
        lines.append(
            f"- pass={fp_gate.get('pass')} · W30 stop-less gross median={fp_gate.get('w30_stop_less_gross_median')} · n={fp_gate.get('n')}"
        )
        diag_key = StfParams(
            FINGERPRINT_ATR_PERIOD,
            FINGERPRINT_ST_MULT,
            FINGERPRINT_COOLDOWN_BARS,
            FINGERPRINT_K_SL,
            FINGERPRINT_TP_ATR_K,
        ).key()
        diag = (train_payload.get("post_entry_diagnosis_by_param") or {}).get(diag_key)
        if diag:
            lines.extend(format_gate_report_post_entry_section(diag, param_label="fingerprint"))
    else:
        lines.extend(["", "## Grid (0c-2)", ""])
        best = t_gate.get("best_passing")
        if best:
            lines.append(f"- best_passing: {best}")
        else:
            lines.append("- **無通過組** — 若 fingerprint 已過 → `stf_fingerprint_pass_g1_fail`")

    lines.extend(
        [
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )
    if mode == "fingerprint":
        if fp_gate.get("pass"):
            lines.append("| 決策 | **Proceed 0c-2 grid** — fingerprint W30 median > 0 |")
        else:
            lines.append("| 決策 | **MVPClosed at 0c-1** — fingerprint 未過 |")
    elif t_gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — supertrend-flip plugin |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0 grid** |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "stf-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-013 SuperTrend flip counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2025-01-01")
    parser.add_argument("--train-to", default="2025-12-31")
    parser.add_argument("--valid-from", default="2026-01-01")
    parser.add_argument("--valid-to", default="2026-03-31")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fingerprint-only",
        action="store_true",
        help="0c-1 single-point fingerprint (default)",
    )
    mode_group.add_argument("--grid", action="store_true", help="0c-2 full param grid")
    args = parser.parse_args(argv)

    mode = "grid" if args.grid else "fingerprint"
    common = dict(code=args.code, cache_dir=args.cache_dir, mode=mode)

    train_payload = build_stf_payload(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )
    valid_payload = build_stf_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    if mode == "fingerprint":
        train_path = reports / "counterfactual_stf_fingerprint.json"
    else:
        train_path = reports / "counterfactual_stf_train.json"
    valid_path = reports / "counterfactual_stf_valid.json"

    train_path.write_text(
        json.dumps(_payload_for_json(train_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(_payload_for_json(valid_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    train_compact = _compact(train_payload)
    valid_compact = _compact(valid_payload)
    gate_path = ws / "gate_report.md"
    _write_gate_report(
        gate_path,
        train=train_compact,
        valid=valid_compact,
        train_payload=train_payload,
        valid_payload=valid_payload,
        mode=mode,
    )

    if mode == "fingerprint":
        fp = train_payload.get("fingerprint_gate") or {}
        print(
            f"fingerprint pass={fp.get('pass')} W30_med={fp.get('w30_stop_less_gross_median')} "
            f"n={fp.get('n')} -> {train_path}",
            flush=True,
        )
    else:
        t_gate = train_payload["phase0_gate"]
        print(
            f"grid pass={t_gate['pass']} best={t_gate.get('best_passing')} -> {train_path}",
            flush=True,
        )
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
