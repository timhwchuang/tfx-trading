"""FT-014 Phase 0: Morning VWAP hold pullback counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.morning_vwap_hold_pullback_counterfactual import (
    EXIT_VARIANT,
    FINGERPRINT_HOLD_MIN_BARS,
    FINGERPRINT_K_SL,
    FINGERPRINT_PULLBACK_VOL_RATIO_MAX,
    FINGERPRINT_TP_ATR_K,
    FINGERPRINT_TOUCH_BUF_K,
    FINGERPRINT_VWAP_SLOPE_BARS,
    MvhpParams,
    build_mvhp_payload,
)
from reporting.post_entry_diagnosis import format_gate_report_post_entry_section


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact(payload: dict) -> dict:
    gate = payload.get("phase0_gate") or {}
    fp = payload.get("fingerprint_gate")
    key = None
    if payload.get("fingerprint_params"):
        key = MvhpParams(
            FINGERPRINT_HOLD_MIN_BARS,
            FINGERPRINT_TOUCH_BUF_K,
            FINGERPRINT_PULLBACK_VOL_RATIO_MAX,
            FINGERPRINT_VWAP_SLOPE_BARS,
            FINGERPRINT_K_SL,
            FINGERPRINT_TP_ATR_K,
        ).key()
    return {
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
        "variant": payload.get("variant"),
        "mode": payload.get("mode"),
        "phase0_pass": gate.get("pass"),
        "best_passing": gate.get("best_passing"),
        "fingerprint_pass": fp.get("pass") if fp else None,
        "outcome_hint": payload.get("outcome_hint"),
        "summary_by_param": {
            k: v.get(EXIT_VARIANT) for k, v in (payload.get("summary_by_param") or {}).items()
        },
        "entry_count_by_param": payload.get("entry_count_by_param"),
        "funnel_by_param": payload.get("funnel_by_param"),
        "fingerprint_param_key": key,
    }


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
    fingerprint_passed_for_grid: bool | None = None,
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    fp_gate = train_payload.get("fingerprint_gate") or {}
    fp_key = MvhpParams(
        FINGERPRINT_HOLD_MIN_BARS,
        FINGERPRINT_TOUCH_BUF_K,
        FINGERPRINT_PULLBACK_VOL_RATIO_MAX,
        FINGERPRINT_VWAP_SLOPE_BARS,
        FINGERPRINT_K_SL,
        FINGERPRINT_TP_ATR_K,
    ).key()

    lines = [
        "# FT-014 Gate Report — mvhp-baseline（Phase 0）",
        "",
        "> **Thesis P-004**：Morning VWAP hold pullback — long-only Phase 0。",
        "> **Entry**：raw 1m bar close（ORB/VSF 同族 · 無 FT-013 entry+1）。",
        "> **Exit**：`atr_barrier_900s` · max_hold_sec=900。",
        "",
        "## Phase 0b — Code review",
        "",
        "| MUST | 結果 |",
        "|------|------|",
        "| MUST-1 hold + slope + first touch | PASS（agent 2026-06-28） |",
        "| MUST-2 摩擦 5 | PASS |",
        "| MUST-3 funnel 絕對數 | PASS |",
        "| post_entry hook | PASS |",
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
                f"- session_days={funnel.get('days_with_session')} → hold_pass={funnel.get('hold_pass')} → "
                f"first_touch={funnel.get('first_touch')} → vol_shrink={funnel.get('vol_shrink')} → "
                f"entry={funnel.get('entry')}",
                f"- hold→entry rate={funnel.get('hold_to_entry_rate')}",
                "",
            ]
        )
        diag = (train_payload.get("post_entry_diagnosis_by_param") or {}).get(fp_key)
        if diag:
            lines.extend(format_gate_report_post_entry_section(diag, param_label="fingerprint"))
        lines.extend(["## Grid (0c-2)", "", "*未執行 — 0c-1 結果見 §Decision*", ""])
    else:
        lines.extend(["## Fingerprint (0c-1)", "", f"- 已通過：{fingerprint_passed_for_grid}", ""])
        lines.extend(
            [
                "## Grid (0c-2)",
                "",
                "| param | n | gross/趟 | net/趟 |",
                "|---|---:|---:|---:|",
            ]
        )
        for param, s in sorted((train_payload.get("summary_by_param") or {}).items()):
            block = (s or {}).get(EXIT_VARIANT) or {}
            if not block:
                continue
            lines.append(
                f"| {param} | {block.get('n', '—')} | {block.get('gross_mean', '—')} | "
                f"{block.get('net_mean', '—')} |"
            )
        best = t_gate.get("best_passing")
        lines.extend(["", f"**best_passing**: {best or '—'}", ""])
        s31 = train_payload.get("section31_long_by_param") or {}
        if best:
            b = s31.get(best["param"], {})
            lines.extend(
                [
                    "## §3.1 disqualify（Long · best_passing）",
                    "",
                    f"- disqualified={b.get('disqualified')} reasons={b.get('reasons')}",
                    "",
                ]
            )

    vs = (valid_payload.get("summary_by_param") or {}).get(fp_key, {}).get(EXIT_VARIANT, {})
    vfp = valid_payload.get("fingerprint_gate") or {}
    lines.extend(
        [
            "## Valid 2026 Q1（參考 only）",
            "",
            f"- n={vs.get('n', '—')} · gross/趟={vs.get('gross_mean', '—')} · net/趟={vs.get('net_mean', '—')}",
            f"- W30 stop-less med={vfp.get('w30_stop_less_gross_median', '—')}",
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
            lines.append("| 決策 | **MVPClosed** — `mvhp_fingerprint_fail` |")
            outcome = "mvhp_fingerprint_fail"
    elif t_gate.get("pass"):
        lines.append("| 決策 | **Go Phase 1 候選** — grid 通過 · 待人類 Go |")
        outcome = "grid_pass"
    else:
        lines.append("| 決策 | **MVPClosed** — `mvhp_fingerprint_pass_g1_fail` |")
        outcome = "mvhp_fingerprint_pass_g1_fail"

    lines.extend(
        [
            f"| outcome | `{outcome}` |",
            "| UAT | **維持** `strategy-vwap-momentum` |",
            "| Pilot 備註 | bar close vs IOC ±3 未模擬 |",
            "| 日期 | 2026-06-28 |",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "mvhp-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-014 MVHP counterfactual")
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

    train_payload = build_mvhp_payload(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )
    valid_payload = build_mvhp_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    if mode == "fingerprint":
        train_path = reports / "counterfactual_mvhp_fingerprint.json"
    else:
        train_path = reports / "counterfactual_mvhp_train.json"
    valid_path = reports / "counterfactual_mvhp_valid.json"

    train_path.write_text(
        json.dumps(_payload_for_json(train_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(_payload_for_json(valid_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fp_pass = (train_payload.get("fingerprint_gate") or {}).get("pass") if mode == "fingerprint" else None
    gate_path = ws / "gate_report.md"
    _write_gate_report(
        gate_path,
        train_payload=train_payload,
        valid_payload=valid_payload,
        mode=mode,
        fingerprint_passed_for_grid=fp_pass,
    )

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
