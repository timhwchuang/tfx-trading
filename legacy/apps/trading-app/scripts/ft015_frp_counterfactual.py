"""FT-015 Phase 0: FVG retest pullback counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.fvg_retest_pullback_counterfactual import (
    EXIT_VARIANT,
    FINGERPRINT_K_SL,
    FINGERPRINT_MAX_FVG_AGE_BARS,
    FINGERPRINT_SWING_LOOKBACK,
    FINGERPRINT_TP_ATR_K,
    FINGERPRINT_VOL_PCT_MAX,
    FrpParams,
    build_frp_payload,
)
from reporting.post_entry_diagnosis import format_gate_report_post_entry_section


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _payload_for_json(payload: dict) -> dict:
    out = dict(payload)
    out.pop("rows_by_param", None)
    return out


def _write_gate_report(
    path: Path,
    *,
    train_payload: dict,
    valid_payload: dict,
    mode: str,
) -> None:
    fp_gate = train_payload.get("fingerprint_gate") or {}
    fp_key = FrpParams(
        FINGERPRINT_SWING_LOOKBACK,
        FINGERPRINT_MAX_FVG_AGE_BARS,
        FINGERPRINT_VOL_PCT_MAX,
        FINGERPRINT_K_SL,
        FINGERPRINT_TP_ATR_K,
    ).key()
    t_gate = train_payload["phase0_gate"]

    lines = [
        "# FT-015 Gate Report — fvg-baseline（Phase 0 · skew）",
        "",
        "> **Thesis P-009**：BOS → unmitigated FVG → zone retest + vol_1s ≤ p40。",
        "> **Entry**：tick in FVG zone · 順 BOS 方向 · **雙向**。",
        "> **Exit**：`atr_barrier_900s` · G3S **n≥15**。",
        "",
        "## Phase 0b — Code review",
        "",
        "| MUST | 結果 |",
        "|------|------|",
        "| MUST-1 FT-002 §4.7 FVG/BOS | PASS（agent 2026-06-28） |",
        "| MUST-2 摩擦 5 · tick entry | PASS |",
        "| MUST-3 funnel + post_entry | PASS |",
        "| skew §3.2 appendix | PASS |",
        "",
    ]

    if mode == "fingerprint":
        s = (train_payload.get("summary_by_param") or {}).get(fp_key, {}).get(EXIT_VARIANT, {})
        lines.extend(
            [
                "## Fingerprint (0c-1)",
                "",
                f"| 區間 | W30 stop-less med | n (G3S≥15) | barrier gross/趟 | 判定 |",
                f"|------|-------------------|------------|----------------|------|",
                f"| Train {train_payload['from_date']}～{train_payload['to_date']} | "
                f"{fp_gate.get('w30_stop_less_gross_median', '—')} | {fp_gate.get('n', '—')} | "
                f"{s.get('gross_mean', '—')} | **{'通過' if fp_gate.get('pass') else '未過'}** |",
                "",
            ]
        )
        funnel = (train_payload.get("funnel_by_param") or {}).get(fp_key, {}).get("totals") or {}
        lines.extend(
            [
                "### Funnel（絕對數）",
                "",
                f"- session_days={funnel.get('days_with_session')} → bos_active_fvg={funnel.get('bos_active_fvg')} → "
                f"zone_touch={funnel.get('zone_touch')} → vol_ok={funnel.get('vol_ok')} → entry={funnel.get('entry')}",
                "",
            ]
        )
        diag = (train_payload.get("post_entry_diagnosis_by_param") or {}).get(fp_key)
        if diag:
            lines.extend(format_gate_report_post_entry_section(diag, param_label="fingerprint"))
        lines.extend(["## Grid (0c-2)", "", "*未執行 — 0c-1 結果見 §Decision*", ""])
    else:
        lines.extend(["## Fingerprint (0c-1)", "", "（見 fingerprint JSON）", "", "## Grid (0c-2)", ""])
        for param, s in sorted((train_payload.get("summary_by_param") or {}).items()):
            block = (s or {}).get(EXIT_VARIANT) or {}
            if not block:
                continue
            lines.append(
                f"- `{param}`: n={block.get('n')} gross={block.get('gross_mean')} net={block.get('net_mean')}"
            )
        best = t_gate.get("best_passing")
        skew = (train_payload.get("skew_gate_by_param") or {}).get((best or {}).get("param", ""), {})
        lines.extend(
            [
                "",
                f"**best_passing**: {best}",
                f"**skew_gate**: disqualified={skew.get('disqualified')} reasons={skew.get('reasons')}",
                "",
            ]
        )

    vs = (valid_payload.get("summary_by_param") or {}).get(fp_key, {}).get(EXIT_VARIANT, {})
    lines.extend(
        [
            "## Valid 2026 Q1（參考 only · skew valid≤0 禁 holdout）",
            "",
            f"- n={vs.get('n', '—')} · gross/趟={vs.get('gross_mean', '—')} · net/趟={vs.get('net_mean', '—')}",
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )

    outcome = train_payload.get("outcome_hint") or "pending"
    if mode == "fingerprint":
        if fp_gate.get("pass"):
            lines.append("| 決策 | **Proceed 0c-2 grid** |")
            outcome = "fingerprint_pass"
        else:
            lines.append("| 決策 | **MVPClosed** — `frp_fingerprint_fail` |")
            outcome = "frp_fingerprint_fail"
    elif t_gate.get("pass"):
        lines.append("| 決策 | **Go Phase 1 候選** — grid 通過 · 待人類 Go |")
        outcome = "grid_pass"
    else:
        lines.append("| 決策 | **MVPClosed** — `frp_fingerprint_pass_g1_fail` |")
        outcome = "frp_fingerprint_pass_g1_fail"

    lines.extend(
        [
            f"| outcome | `{outcome}` |",
            "| thesis_class | **skew** |",
            "| UAT | **維持** `strategy-vwap-momentum` |",
            "| 日期 | 2026-06-28 |",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "fvg-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-015 FVG retest pullback counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2025-01-01")
    parser.add_argument("--train-to", default="2025-12-31")
    parser.add_argument("--valid-from", default="2026-01-01")
    parser.add_argument("--valid-to", default="2026-03-31")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--fingerprint-only", action="store_true")
    mode_group.add_argument("--grid", action="store_true")
    args = parser.parse_args(argv)

    mode = "grid" if args.grid else "fingerprint"
    common = dict(code=args.code, cache_dir=args.cache_dir, mode=mode)

    train_payload = build_frp_payload(from_date=args.train_from, to_date=args.train_to, **common)
    valid_payload = build_frp_payload(from_date=args.valid_from, to_date=args.valid_to, **common)

    reports.mkdir(parents=True, exist_ok=True)
    train_path = (
        reports / "counterfactual_frp_train.json"
        if mode == "grid"
        else reports / "counterfactual_frp_fingerprint.json"
    )
    valid_path = reports / "counterfactual_frp_valid.json"
    train_path.write_text(
        json.dumps(_payload_for_json(train_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(_payload_for_json(valid_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    gate_path = ws / "gate_report.md"
    _write_gate_report(gate_path, train_payload=train_payload, valid_payload=valid_payload, mode=mode)

    if mode == "fingerprint":
        fp = train_payload.get("fingerprint_gate") or {}
        print(
            f"fingerprint pass={fp.get('pass')} W30_med={fp.get('w30_stop_less_gross_median')} "
            f"n={fp.get('n')} -> {train_path}",
            flush=True,
        )
    else:
        print(
            f"grid pass={train_payload['phase0_gate']['pass']} "
            f"best={train_payload['phase0_gate'].get('best_passing')} -> {train_path}",
            flush=True,
        )
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
