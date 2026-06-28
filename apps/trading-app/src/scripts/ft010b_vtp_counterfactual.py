"""FT-010b falsification: buffer-touch only (no volume shrink / attack filter)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.vwap_trend_pullback_counterfactual import EXIT_VARIANT, build_vtp_payload

VARIANT = "v1b_buffer_touch_no_vol"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compact(payload: dict) -> dict:
    gate = payload.get("phase0_gate") or {}
    return {
        "variant": payload.get("variant"),
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
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
    baseline_train: dict | None,
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    t_funnel = train_payload.get("funnel") or {}
    lines = [
        "# FT-010b Gate Report — vtp-baseline（falsification）",
        "",
        "> **Thesis G-b**：與 FT-010 相同，但 **移除**縮量 + 攻擊量門檻（FT-003 診斷：vol 非瓶頸）。",
        "> **主判**：**01–03 合計** · 04 valid 參考。",
        "",
        "## vs FT-010a（有量能濾網）",
        "",
    ]
    if baseline_train:
        lines.append("| 版本 | 01–03 總 n（rcy6+8+10） | 備註 |")
        lines.append("|------|----------------------|------|")
        a_n = sum((baseline_train.get("entry_count_by_param") or {}).values())
        b_n = sum((train.get("entry_count_by_param") or {}).values())
        lines.append(f"| FT-010a | {a_n} | 原 SPEC |")
        lines.append(f"| **FT-010b** | **{b_n}** | 本報告 |")
        lines.append("")

    lines.extend(
        [
            "| 區間 | 產物 | Phase 0 |",
            "|------|------|---------|",
            f"| **01–03** {train['from_date']}～{train['to_date']} | "
            f"[`counterfactual_vtp_010b_0103.json`](reports/counterfactual_vtp_010b_0103.json) | "
            f"**{'通過' if t_gate['pass'] else '未過'}** |",
            f"| Valid {valid['from_date']}～{valid['to_date']} | "
            f"[`counterfactual_vtp_010b_valid.json`](reports/counterfactual_vtp_010b_valid.json) | "
            f"{'通過' if v_gate['pass'] else '未過'}（參考） |",
            "",
            "## Funnel（01–03）",
            "",
            f"- stretch→buffer rate: {t_funnel.get('stretch_to_buffer_rate')}",
            "",
            "## 01–03 — summary_by_param",
            "",
            "| param | n | gross/趟 | net/趟 | QSL |",
            "|---|---|----------|--------|-----|",
        ]
    )
    for param, s in sorted(train.get("summary_by_param", {}).items()):
        if not s:
            continue
        lines.append(
            f"| {param} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | "
            f"{s.get('net_mean', '—')} | {s.get('quick_stop_loss_rate', '—')} |"
        )

    best = t_gate.get("best_passing")
    lines.extend(["", "### Best passing（01–03）", ""])
    if best:
        lines.append(
            f"- {best['param']}: n={best['n']} gross={best['gross_mean']} net={best['net_mean']}"
        )
    else:
        lines.append("**無通過組。**")

    lines.extend(
        [
            "",
            "## Valid 2026-04",
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
        lines.append("| 決策 | **Go 新 SPEC** — 量能非必要；可開 FT-010b plugin 設計 |")
    else:
        lines.append("| 決策 | **仍 No-Go** — 砍 vol 仍無法 G1–G3；回踩 thesis 結構性死亡 |")
    lines.append("| 備註 | 010b 為 pre-registered falsification，非 010a 事後 tune |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "vtp-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-010b VTP falsification (no volume filter)")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2026-01-01")
    parser.add_argument("--train-to", default="2026-03-31")
    parser.add_argument("--valid-from", default="2026-04-01")
    parser.add_argument("--valid-to", default="2026-04-30")
    args = parser.parse_args(argv)

    cf = dict(
        require_volume_filter=False,
        variant=VARIANT,
    )
    common = dict(code=args.code, cache_dir=args.cache_dir, **cf)

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

    baseline_train: dict | None = None
    baseline_path = reports / "counterfactual_vtp_0103.json"
    if baseline_path.is_file():
        baseline_train = json.loads(baseline_path.read_text(encoding="utf-8"))

    reports.mkdir(parents=True, exist_ok=True)
    train_path = reports / "counterfactual_vtp_010b_0103.json"
    valid_path = reports / "counterfactual_vtp_010b_valid.json"
    for path, payload in ((train_path, train_payload), (valid_path, valid_payload)):
        out = dict(payload)
        out.pop("rows_by_param", None)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    train_compact = _compact(train_payload)
    valid_compact = _compact(valid_payload)
    gate_path = ws / "gate_report_010b.md"
    _write_gate_report(
        gate_path,
        train=train_compact,
        valid=valid_compact,
        train_payload=train_payload,
        valid_payload=valid_payload,
        baseline_train=baseline_train,
    )

    t_gate = train_payload["phase0_gate"]
    print(
        f"010b 01-03 pass={t_gate['pass']} best={t_gate.get('best_passing')} -> {train_path}",
        flush=True,
    )
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
