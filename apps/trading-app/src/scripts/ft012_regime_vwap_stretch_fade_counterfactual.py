"""FT-012 Phase 0: Regime VWAP stretch fade counterfactual CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reporting.regime_vwap_stretch_fade_counterfactual import (
    EXIT_VARIANT,
    build_regime_vwap_stretch_fade_payload,
    build_vsf_delta_with_rvsf,
)


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
        "candidates": gate.get("candidates"),
        "summary_by_param": {
            k: v.get(EXIT_VARIANT) for k, v in (payload.get("summary_by_param") or {}).items()
        },
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
    vsf_delta: dict,
    code_review_pass: str = "pending",
) -> None:
    t_gate = train_payload["phase0_gate"]
    v_gate = valid_payload["phase0_gate"]
    lines = [
        "# FT-012 Gate Report — rvsf-baseline（Phase 0）",
        "",
        f"> **Code review**：{code_review_pass}",
        "> **Thesis I**：Regime VWAP Stretch Fade — P-001 GO。",
        "> **主判**：**2025 train**（Holdout v2.1）· 2026 Q1 valid 診斷。",
        "",
        "| 區間 | 產物 | Phase 0 |",
        "|------|------|---------|",
        f"| **Train** {train['from_date']}～{train['to_date']} | "
        f"[`counterfactual_rvsf_train.json`](reports/counterfactual_rvsf_train.json) | "
        f"**{'通過' if t_gate['pass'] else '未過'}** |",
        f"| Valid {valid['from_date']}～{valid['to_date']} | "
        f"[`counterfactual_rvsf_valid.json`](reports/counterfactual_rvsf_valid.json) | "
        f"{'通過' if v_gate['pass'] else '未過'}（診斷） |",
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
            "## VSF delta（train · 早盤 09:00–10:30 · k=2.0 · 無 regime）",
            "",
            f"- VSF morning n={vsf_delta.get('vsf_morning', {}).get('n')} "
            f"net_total={vsf_delta.get('vsf_morning', {}).get('net_total')}",
            f"- RVSF best: {vsf_delta.get('rvsf_best')}",
            f"- Delta: {vsf_delta.get('delta')}",
            "",
            "## Valid 2026 Q1（診斷 only）",
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
        lines.append("| 決策 | **Go Phase 1** — regime-vwap-stretch-fade plugin |")
    else:
        lines.append("| 決策 | **No-Go at Phase 0** (`thesis_i_rvsf_no_go`) |")
    if t_gate["pass"] and not v_gate["pass"]:
        v_best = v_gate.get("best_passing")
        if v_best and (v_best.get("net_mean") or 0) <= 0:
            lines.append("| 備註 | train 過但 valid Q1 net ≤ 0 — **overfit_suspect** |")
    elif not t_gate["pass"] and v_gate.get("pass"):
        lines.append("| 備註 | valid 過但 train 未過 — **overfit_suspect** |")
    lines.append("| UAT | **維持** `strategy-vwap-momentum` smoke |")
    lines.append("| 日期 | 2026-06-28 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _payload_for_json(payload: dict) -> dict:
    out = dict(payload)
    out.pop("rows_by_param", None)
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    ws = root / "workspaces" / "rvsf-baseline"
    reports = ws / "reports"
    parser = argparse.ArgumentParser(description="FT-012 RVSF counterfactual")
    parser.add_argument("--code", default="TMFR1")
    parser.add_argument("--cache-dir", type=Path, default=root / "tick_cache")
    parser.add_argument("--train-from", default="2025-01-01")
    parser.add_argument("--train-to", default="2025-12-31")
    parser.add_argument("--valid-from", default="2026-01-01")
    parser.add_argument("--valid-to", default="2026-03-31")
    parser.add_argument("--stretch-k", type=float, nargs="*", default=[2.0, 2.5, 3.0])
    parser.add_argument("--vol-pct-max", type=int, nargs="*", default=[25, 30, 35])
    parser.add_argument(
        "--code-review-pass",
        default="pending",
        help="Record Phase 0b review status in gate_report",
    )
    args = parser.parse_args(argv)

    common = dict(
        code=args.code,
        cache_dir=args.cache_dir,
        stretch_ks=tuple(args.stretch_k),
        vol_pct_maxs=tuple(args.vol_pct_max),
    )

    train_payload = build_regime_vwap_stretch_fade_payload(
        from_date=args.train_from,
        to_date=args.train_to,
        **common,
    )
    valid_payload = build_regime_vwap_stretch_fade_payload(
        from_date=args.valid_from,
        to_date=args.valid_to,
        **common,
    )
    vsf_delta = build_vsf_delta_with_rvsf(
        train_payload,
        code=args.code,
        cache_dir=args.cache_dir,
        from_date=args.train_from,
        to_date=args.train_to,
        stretch_k=2.0,
    )

    reports.mkdir(parents=True, exist_ok=True)
    train_path = reports / "counterfactual_rvsf_train.json"
    valid_path = reports / "counterfactual_rvsf_valid.json"
    train_path.write_text(
        json.dumps(_payload_for_json(train_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    valid_path.write_text(
        json.dumps(_payload_for_json(valid_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    funnel_path = reports / "entry_funnel_rvsf.json"
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

    delta_path = reports / "rvsf_vs_vsf_delta.json"
    delta_path.write_text(
        json.dumps(vsf_delta, ensure_ascii=False, indent=2),
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
        vsf_delta=vsf_delta,
        code_review_pass=args.code_review_pass,
    )

    t_gate = train_payload["phase0_gate"]
    print(
        f"train pass={t_gate['pass']} best={t_gate.get('best_passing')} -> {train_path}",
        flush=True,
    )
    print(f"valid Q1 pass={valid_payload['phase0_gate']['pass']}", flush=True)
    print(f"VSF delta: {delta_path}", flush=True)
    print(f"Gate report: {gate_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
