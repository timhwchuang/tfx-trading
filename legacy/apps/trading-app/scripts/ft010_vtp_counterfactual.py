"""FT-010 Phase 0: VWAP trend pullback counterfactual CLI (01-03 primary · 04 valid)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.vwap_trend_pullback_counterfactual import EXIT_VARIANT, build_vtp_payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact(payload: dict) -> dict:
    gate = payload.get("phase0_gate") or {}
    return {
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
        "variant": payload.get("variant"),
        "direction": payload.get("direction"),
        "phase0_pass": gate.get("pass"),
        "best_passing": gate.get("best_passing"),
        "summary_by_param": {
            k: v.get(EXIT_VARIANT) for k, v in (payload.get("summary_by_param") or {}).items()
        },
        "entry_count_by_param": payload.get("entry_count_by_param"),
        "funnel": payload.get("funnel"),
    }


def _write_gate_report(
    path: Path,
    *,
    train: dict,
    valid: dict,
    train_payload: dict,
    valid_payload: dict,
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    t_funnel = train_payload.get("funnel") or {}
    lines = [
        "# FT-010 Gate Report — vtp-baseline（Phase 0）",
        "",
        "> **Thesis G**：VWAP Trend Pullback — Phase 0 **long-only**。",
        "> **主判**：**01–03 合計** · 04 valid 參考。",
        "",
        "| 區間 | 產物 | Phase 0 |",
        "|------|------|---------|",
        f"| **01–03** {train['from_date']}～{train['to_date']} | "
        f"[`counterfactual_vtp_0103.json`](reports/counterfactual_vtp_0103.json) | "
        f"**{'通過' if t_gate['pass'] else '未過'}** |",
        f"| Valid {valid['from_date']}～{valid['to_date']} | "
        f"[`counterfactual_vtp_valid.json`](reports/counterfactual_vtp_valid.json) | "
        f"{'通過' if v_gate['pass'] else '未過'}（參考） |",
        "",
        "## Funnel（01–03）",
        "",
        f"- trading_days: {t_funnel.get('trading_days')}",
        f"- days_with_stretch_env: {t_funnel.get('days_with_stretch_env')}",
        f"- days_with_buffer_touch: {t_funnel.get('days_with_buffer_touch')}",
        f"- stretch→buffer rate: {t_funnel.get('stretch_to_buffer_rate')}",
        f"- structural_band_unreachable: {t_funnel.get('structural_band_unreachable')}",
        "",
        "## 01–03 主判 — summary_by_param",
        "",
        "| param | n | gross/趟 | net/趟 | QSL |",
        "|---|---|----------|--------|-----|",
    ]
    for param, s in sorted(train.get("summary_by_param", {}).items()):
        if not s:
            continue
        qsl = s.get("quick_stop_loss_rate", "—")
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | "
            f"{s.get('net_mean', '—')} | {qsl} |"
        )

    best_t = t_gate.get("best_passing")
    lines.extend(["", "### Best passing（01–03）", ""])
    if best_t:
        lines.append(
            f"- {best_t['param']}: n={best_t['n']} gross={best_t['gross_mean']} net={best_t['net_mean']}"
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
    if t_gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — vwap-trend-pullback plugin |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_g_vtp_no_go`) |")
    if v_gate["pass"] and not t_gate["pass"]:
        lines.append("| 備註 | valid 過但 01–03 未過 — overfit suspect |")
    elif t_gate["pass"] and not v_gate["pass"]:
        v_best = v_gate.get("best_passing")
        if v_best and (v_best.get("net_mean") or 0) <= 0:
            lines.append("| 備註 | 01–03 過但 04 valid net ≤ 0 — 謹慎推進 |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _payload_for_json(payload: dict) -> dict:
    """Drop per-trade rows from written JSON (summary retained)."""
    out = dict(payload)
    out.pop("rows_by_param", None)
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "vtp-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-010 VWAP trend pullback counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2026-01-01")
    parser.add_argument("--train-to", default="2026-03-31")
    parser.add_argument("--valid-from", default="2026-04-01")
    parser.add_argument("--valid-to", default="2026-04-30")
    args = parser.parse_args(argv)

    common = dict(code=args.code, cache_dir=args.cache_dir)

    train_payload = build_vtp_payload(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )
    valid_payload = build_vtp_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    train_path = reports / "counterfactual_vtp_0103.json"
    valid_path = reports / "counterfactual_vtp_valid.json"
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
    funnel_path = reports / "entry_funnel_vtp.json"
    funnel_path.write_text(
        json.dumps(
            {
                "train_0103": train_compact.get("funnel"),
                "valid_2026_04": valid_compact.get("funnel"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    gate_path = ws / "gate_report.md"
    _write_gate_report(
        gate_path,
        train=train_compact,
        valid=valid_compact,
        train_payload=train_payload,
        valid_payload=valid_payload,
    )

    t_gate = train_payload["phase0_gate"]
    print(
        f"01-03 pass={t_gate['pass']} best={t_gate.get('best_passing')} -> {train_path}",
        flush=True,
    )
    print(f"04 valid pass={valid_payload['phase0_gate']['pass']}", flush=True)
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
