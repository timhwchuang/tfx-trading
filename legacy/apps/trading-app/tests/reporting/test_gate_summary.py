"""Tests for reporting.gate_summary (Playbook v1.7)."""

from __future__ import annotations

import json
from pathlib import Path

from reporting.gate_summary import (
    build_gate_summary,
    extract_contract_metrics,
    format_gate_report_table,
    is_contract_exit_key,
    pick_champion,
)

REPO = Path(__file__).resolve().parents[4]
GUDT_TRAIN = REPO / "workspaces/gudt-baseline/reports/counterfactual_gudt_train.json"
SFBT_FP = REPO / "workspaces/sfbt-baseline/reports/counterfactual_sfbt_fingerprint.json"
VSF_TRAIN = REPO / "workspaces/vsf-baseline/reports/counterfactual_v2.1_train2025.json"
MVHP_FP = REPO / "workspaces/mvhp-baseline/reports/counterfactual_mvhp_fingerprint.json"


def test_is_contract_exit_key():
    assert is_contract_exit_key("atr_barrier_180s")
    assert is_contract_exit_key("atr_trail_skew_900s")
    assert not is_contract_exit_key("horizon_1800s")
    assert not is_contract_exit_key("stop_less_W900")


def test_gudt_train_champion_net_total():
    payload = json.loads(GUDT_TRAIN.read_text(encoding="utf-8"))
    metrics = extract_contract_metrics(payload)
    champion = pick_champion(metrics, payload)
    assert champion is not None
    assert champion.net_total == 173.9
    assert champion.n == 53
    assert champion.net_mean == 3.28

    summary = build_gate_summary(payload)
    assert summary["champion"]["net_total"] == 173.9
    assert summary["outcome_class"] == "skew_profile_fail"


def test_horizon_not_champion_on_vsf():
    payload = json.loads(VSF_TRAIN.read_text(encoding="utf-8"))
    metrics = extract_contract_metrics(payload)
    champion = pick_champion(metrics, payload)
    assert champion is not None
    assert "horizon" not in champion.exit_key.lower()
    assert champion.net_total == 162.2


def test_sfbt_fingerprint_contract_mismatch():
    if not SFBT_FP.is_file():
        return
    payload = json.loads(SFBT_FP.read_text(encoding="utf-8"))
    summary = build_gate_summary(payload)
    assert summary["outcome_class"] == "fingerprint_contract_mismatch"
    assert "FINGERPRINT_TRAP_SUSPECT" in summary["warnings"]


def test_mvhp_fingerprint_fail_is_sample_sparse():
    if not MVHP_FP.is_file():
        return
    payload = json.loads(MVHP_FP.read_text(encoding="utf-8"))
    summary = build_gate_summary(payload)
    assert summary["outcome_class"] == "sample_sparse"


def test_mean_robust_appeal_gudt():
    payload = json.loads(GUDT_TRAIN.read_text(encoding="utf-8"))
    from reporting.gate_summary import evaluate_mean_robust_appeal

    appeal = evaluate_mean_robust_appeal(payload)
    assert appeal["eligible"] is True
    assert appeal["mean_robust_pass"] is True
    assert appeal["disqualify"] == []

    payload = json.loads(GUDT_TRAIN.read_text(encoding="utf-8"))
    summary = build_gate_summary(payload)
    md = format_gate_report_table(summary["champion"])
    assert "**173.9**" in md
    assert "atr_trail_skew_900s" in md
