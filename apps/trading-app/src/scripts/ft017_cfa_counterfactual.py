"""FT-017 Phase 0: Compression flow attack counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.compression_flow_attack_counterfactual import (
    EXIT_VARIANT,
    FINGERPRINT_ATTACK_RATIO_MIN,
    FINGERPRINT_ATR_REGIME_CAP,
    FINGERPRINT_COMPRESS_K,
    FINGERPRINT_MIN_STOP_ATR_K,
    FINGERPRINT_TP_ATR_K,
    CfaParams,
    build_cfa_payload,
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
    fp_key = CfaParams(
        FINGERPRINT_COMPRESS_K,
        FINGERPRINT_ATR_REGIME_CAP,
        FINGERPRINT_ATTACK_RATIO_MIN,
        FINGERPRINT_MIN_STOP_ATR_K,
        FINGERPRINT_TP_ATR_K,
    ).key()
    t_gate = train_payload["phase0_gate"]
    skew_fp = (train_payload.get("skew_gate_by_param") or {}).get(fp_key, {})
    slip_fp = (train_payload.get("entry_slippage_sensitivity_by_param") or {}).get(fp_key, {})

    lines = [
        "# FT-017 Gate Report — cfa-baseline（Phase 0 · skew）",
        "",
        "> **Thesis P-010**：Compression flow attack — 30m compress · quiet/attack tick flow · chase。",
        "> **Entry**：tick chase on attack · **雙向** · friction **5**。",
        "> **Exit**：`atr_barrier_900s` · G3S **n≥15**。",
        "",
        "## Phase 0-design",
        "",
        "| 項目 | 結果 |",
        "|------|------|",
        "| 資深 TXF P0 封印 | PASS（2026-06-28） |",
        "",
        "## Phase 0b — Code review",
        "",
        "| MUST | 結果 |",
        "|------|------|",
        "| MUST-1 compress+regime @ signal_1m | pending |",
        "| MUST-2 quiet/attack 60s · ratio/vol | pending |",
        "| MUST-3 tick chase · 結構 stop · min_stop | pending |",
        "| MUST-4 funnel 六階 | pending |",
        "| MUST-5 post_entry · skew 附錄 | pending |",
        "",
    ]

    if mode == "fingerprint":
        s = (train_payload.get("summary_by_param") or {}).get(fp_key, {}).get(EXIT_VARIANT, {})
        lines.extend(
            [
                "## Fingerprint (0c-1)",
                "",
                f"| 區間 | W30 stop-less med | n | barrier gross/趟 | 判定 |",
                f"|------|-------------------|---|----------------|------|",
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
                f"- session_days={funnel.get('days_with_session')} → compress_pass={funnel.get('compress_pass')} → "
                f"regime_pass={funnel.get('regime_pass')} → quiet_pass={funnel.get('quiet_pass')} → "
                f"attack_signal={funnel.get('attack_signal')} → entry={funnel.get('entry')}",
                "",
            ]
        )
        diag = (train_payload.get("post_entry_diagnosis_by_param") or {}).get(fp_key)
        if diag:
            lines.extend(format_gate_report_post_entry_section(diag, param_label="fingerprint"))
        lines.extend(
            [
                "## Skew 附錄（fingerprint · 診斷）",
                "",
                f"- payoff_ratio={skew_fp.get('payoff_ratio')} · tail_count={skew_fp.get('tail_count')}",
                f"- net_mean@friction7={skew_fp.get('net_mean_at_friction_7')} · "
                f"top3_share={skew_fp.get('top3_win_gross_share')}",
                f"- slippage extra mean net: {slip_fp}",
                "",
                "> execution_margin_thin：tick chase 薄流動性 · Pilot IOC ±3 未在 0c 模擬。",
                "",
                "## Grid (0c-2)",
                "",
                "*未執行 — 0c-1 結果見 §Decision*",
                "",
            ]
        )
    else:
        fp_path = path.parent / "reports" / "counterfactual_cfa_fingerprint.json"
        fp_summary = ""
        if fp_path.is_file():
            fp_payload = json.loads(fp_path.read_text(encoding="utf-8"))
            fp_gate = fp_payload.get("fingerprint_gate") or {}
            fp_summary = (
                f"通過 · W30 med **{fp_gate.get('w30_stop_less_gross_median')}** · "
                f"n={fp_gate.get('n')} · barrier gross/趟 "
                f"{((fp_payload.get('summary_by_param') or {}).get(fp_key, {}).get(EXIT_VARIANT) or {}).get('gross_mean')}"
            )
        lines.extend(
            [
                "## Fingerprint (0c-1)",
                "",
                f"（見 `counterfactual_cfa_fingerprint.json`）· {fp_summary or '—'}",
                "",
                "## Grid (0c-2)",
                "",
            ]
        )
        for param, s in sorted((train_payload.get("summary_by_param") or {}).items()):
            block = (s or {}).get(EXIT_VARIANT) or {}
            if block:
                lines.append(
                    f"- `{param}`: n={block.get('n')} gross={block.get('gross_mean')} "
                    f"net={block.get('net_mean')}"
                )
        lines.append(f"\n**best_passing**: {t_gate.get('best_passing')}\n")

    vs = (valid_payload.get("summary_by_param") or {}).get(fp_key, {}).get(EXIT_VARIANT, {})
    v_net = vs.get("net_mean")
    lines.extend(
        [
            "## Valid 2026 Q1（參考 · skew 硬擋）",
            "",
            f"- n={vs.get('n', '—')} · gross/趟={vs.get('gross_mean', '—')} · net/趟={v_net}",
        ]
    )
    if v_net is not None and float(v_net) <= 0:
        lines.append("- **holdout_blocked_overfit** — valid net≤0 禁 holdout（HOLDOUT v2.2.1 §4）")
    lines.extend(["", "## §Decision", "", "| 欄位 | 值 |", "|------|-----|"])

    outcome = train_payload.get("outcome_hint") or "pending"
    if mode == "fingerprint":
        if fp_gate.get("pass"):
            lines.append("| 決策 | **Proceed 0c-2 grid** |")
            outcome = "fingerprint_pass"
        else:
            lines.append("| 決策 | **MVPClosed** — `cfa_fingerprint_fail` |")
            outcome = "cfa_fingerprint_fail"
    elif t_gate.get("pass"):
        lines.append("| 決策 | **Go Phase 1 候選** — grid 通過 · 待人類 Go |")
    else:
        lines.append("| 決策 | **MVPClosed** — `cfa_fingerprint_pass_g1_fail` |")

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
    ws = root / "workspaces" / "cfa-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-017 CFA counterfactual")
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

    train_payload = build_cfa_payload(from_date=args.train_from, to_date=args.train_to, **common)
    valid_payload = build_cfa_payload(from_date=args.valid_from, to_date=args.valid_to, **common)

    reports.mkdir(parents=True, exist_ok=True)
    train_path = (
        reports / "counterfactual_cfa_train.json"
        if mode == "grid"
        else reports / "counterfactual_cfa_fingerprint.json"
    )
    valid_path = reports / "counterfactual_cfa_valid.json"
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
