"""FT-011 Phase 0: Session Confluence Breakout counterfactual CLI (v2.1 train primary)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.scb_counterfactual import EXIT_VARIANT, build_orb_delta, build_scb_payload


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
        "candidates": gate.get("candidates"),
        "summary_by_param": {
            k: v.get(EXIT_VARIANT) for k, v in (payload.get("summary_by_param") or {}).items()
        },
        "summary_by_session_bucket": payload.get("summary_by_session_bucket"),
        "entry_count_by_param": payload.get("entry_count_by_param"),
        "funnel_by_param": payload.get("funnel_by_param"),
    }


def _write_gate_report(
    path: Path,
    *,
    train: dict,
    valid: dict,
    train_payload: dict,
    valid_payload: dict,
    orb_delta: dict,
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    lines = [
        "# FT-011 Gate Report — scb-baseline（Phase 0）",
        "",
        "> **Thesis H**：Session Confluence Breakout — Phase 0 **long-only**。",
        "> **主判**：**2025 train**（Holdout v2.1）· 2026 Q1 valid 參考。",
        "",
        "| 區間 | 產物 | Phase 0 |",
        "|------|------|---------|",
        f"| **Train** {train['from_date']}～{train['to_date']} | "
        f"[`counterfactual_scb_train.json`](reports/counterfactual_scb_train.json) | "
        f"**{'通過' if t_gate['pass'] else '未過'}** |",
        f"| Valid {valid['from_date']}～{valid['to_date']} | "
        f"[`counterfactual_scb_valid.json`](reports/counterfactual_scb_valid.json) | "
        f"{'通過' if v_gate['pass'] else '未過'}（參考） |",
        "",
        "## Train — summary_by_param",
        "",
        "| param | n | gross/趟 | net/趟 | gross_median | QSL | disqualify |",
        "|---|---|----------|--------|--------------|-----|------------|",
    ]
    for cand in t_gate.get("candidates") or []:
        param = cand["param"]
        s = (train.get("summary_by_param") or {}).get(param) or {}
        qsl = s.get("quick_stop_loss_rate", "—")
        dq = ",".join(cand.get("disqualify") or []) or "—"
        lines.append(
            f"| {param} | {cand.get('n', '—')} | {cand.get('gross_mean', '—')} | "
            f"{cand.get('net_mean', '—')} | {cand.get('gross_median', '—')} | {qsl} | {dq} |"
        )

    best_t = t_gate.get("best_passing")
    lines.extend(["", "### Best passing（train）", ""])
    if best_t:
        lines.append(
            f"- {best_t['param']}: n={best_t['n']} gross={best_t['gross_mean']} "
            f"net={best_t['net_mean']} median={best_t.get('gross_median')}"
        )
        if best_t.get("unstable_months"):
            lines.append(f"- G5 不穩月份: {best_t['unstable_months']}")
    else:
        lines.append("**無通過組。**")

    lines.extend(
        [
            "",
            "## Train — session_bucket（G5-bucket 診斷）",
            "",
        ]
    )
    for param, buckets in sorted((train.get("summary_by_session_bucket") or {}).items()):
        lines.append(f"### {param}")
        lines.append("")
        lines.append("| bucket | n | gross/趟 | net/趟 |")
        lines.append("|---|---|----------|--------|")
        for bucket, metrics in sorted(buckets.items()):
            s = metrics.get(EXIT_VARIANT) or {}
            lines.append(
                f"| {bucket} | {s.get('n', '—')} | {s.get('gross_mean', '—')} | {s.get('net_mean', '—')} |"
            )
        lines.append("")

    lines.extend(
        [
            "## ORB delta（train · long · SCB 窗 · bk=0）",
            "",
            "| param | orb_n | scb_n | filtered | orb_net | scb_net | delta | pass_rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for param, block in sorted((orb_delta.get("by_param") or {}).items()):
        lines.append(
            f"| {param} | {block.get('orb_long_count')} | {block.get('scb_count')} | "
            f"{block.get('orb_filtered_by_confluence')} | {block.get('orb_long_net_total')} | "
            f"{block.get('scb_net_total')} | {block.get('net_delta_scb_minus_orb')} | "
            f"{block.get('scb_pass_rate_of_orb')} |"
        )

    lines.extend(
        [
            "",
            "## Valid 2026 Q1（參考 only）",
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
            "## 冠軍資格",
            "",
            f"- [{'x' if t_gate['pass'] else ' '}] G1–G3",
            f"- [{'x' if best_t and not (best_t.get('disqualify')) else ' '}] §3.1 無 disqualify",
            "",
            "## §Decision",
            "",
            "| 欄位 | 值 |",
            "|------|-----|",
        ]
    )
    if t_gate["pass"]:
        lines.append("| 決策 | **Go Phase 1** — session-confluence-breakout plugin |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_h_scb_no_go`) |")
    if t_gate["pass"] and not v_gate["pass"]:
        v_best = v_gate.get("best_passing")
        if v_best and (v_best.get("net_mean") or 0) <= 0:
            lines.append("| 備註 | train 過但 valid Q1 net ≤ 0 — **overfit_suspect** |")
    elif not t_gate["pass"] and v_gate["pass"]:
        lines.append("| 備註 | valid 過但 train 未過 — 不一致 |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _payload_for_json(payload: dict) -> dict:
    out = dict(payload)
    out.pop("rows_by_param", None)
    return out


def _orb_delta_for_json(orb_delta: dict) -> dict:
    out = dict(orb_delta)
    by_param = {}
    for key, block in (out.get("by_param") or {}).items():
        slim = {k: v for k, v in block.items() if k != "days"}
        by_param[key] = slim
    out["by_param"] = by_param
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "scb-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-011 SCB counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2025-01-01")
    parser.add_argument("--train-to", default="2025-12-31")
    parser.add_argument("--valid-from", default="2026-01-01")
    parser.add_argument("--valid-to", default="2026-03-31")
    parser.add_argument("--opening-range-minutes", type=int, nargs="*", default=[20, 30])
    args = parser.parse_args(argv)

    common = dict(
        code=args.code,
        cache_dir=args.cache_dir,
        range_minutes=tuple(args.opening_range_minutes),
    )

    train_payload = build_scb_payload(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )
    valid_payload = build_scb_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )
    orb_delta = build_orb_delta(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )

    reports.mkdir(parents=True, exist_ok=True)
    train_path = reports / "counterfactual_scb_train.json"
    valid_path = reports / "counterfactual_scb_valid.json"
    train_path.write_text(
        json.dumps(_payload_for_json(train_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(_payload_for_json(valid_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    funnel_path = reports / "entry_funnel_scb.json"
    funnel_path.write_text(
        json.dumps(
            {
                "train": train_payload.get("funnel_by_param"),
                "valid": valid_payload.get("funnel_by_param"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    orb_delta_path = reports / "scb_vs_orb_delta.json"
    orb_delta_path.write_text(
        json.dumps(_orb_delta_for_json(orb_delta), ensure_ascii=False, indent=2),
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
        orb_delta=orb_delta,
    )

    t_gate = train_payload["phase0_gate"]
    print(
        f"train pass={t_gate['pass']} best={t_gate.get('best_passing')} -> {train_path}",
        flush=True,
    )
    print(f"valid Q1 pass={valid_payload['phase0_gate']['pass']}", flush=True)
    print(f"ORB delta: {orb_delta_path}", flush=True)
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
