"""Shared gate summary extraction for Alpha counterfactual JSON (Playbook v1.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NON_CONTRACT_SUBSTRINGS = (
    "horizon",
    "stop_less",
    "stopless",
    "post_entry",
    "forward",
)

CONTRACT_SUBSTRINGS = (
    "barrier",
    "trail",
    "atr_barrier",
    "atr_trail",
    "fvg_mid",
)

JOINT_CONTRACT_GROSS_FLOOR = 3.0
FINGERPRINT_TRAP_GROSS_CEILING = 3.0


@dataclass
class ParamMetrics:
    param: str
    exit_key: str
    path: str
    n: int
    gross_mean: float | None
    net_mean: float | None
    gross_total: float | None
    net_total: float | None


@dataclass
class ChampionRow:
    param: str
    exit_key: str
    path: str
    n: int
    gross_mean: float | None
    net_mean: float | None
    gross_total: float | None
    net_total: float | None
    contract_exit: str | None = None


def is_contract_exit_key(key: str) -> bool:
    lower = key.lower()
    if any(s in lower for s in NON_CONTRACT_SUBSTRINGS):
        return False
    return any(s in lower for s in CONTRACT_SUBSTRINGS)


def contract_exit_from_payload(payload: dict[str, Any]) -> str | None:
    sim = payload.get("sim_params") or {}
    if sim.get("exit_variant"):
        return str(sim["exit_variant"])
    return None


def _metric_from_dict(
    obj: dict[str, Any],
    *,
    param: str,
    exit_key: str,
    path: str,
) -> ParamMetrics | None:
    n = obj.get("n")
    if not n:
        return None
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return None
    if n_int <= 0:
        return None
    return ParamMetrics(
        param=param,
        exit_key=exit_key,
        path=path,
        n=n_int,
        gross_mean=_as_float(obj.get("gross_mean")),
        net_mean=_as_float(obj.get("net_mean")),
        gross_total=_as_float(obj.get("gross_total")),
        net_total=_as_float(obj.get("net_total")),
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_contract_metrics(payload: dict[str, Any]) -> list[ParamMetrics]:
    """Collect contract-exit rows from counterfactual JSON (excludes horizon / stop-less)."""
    preferred_exit = contract_exit_from_payload(payload)
    found: list[ParamMetrics] = []

    def walk(obj: Any, path: str = "", param: str = "") -> None:
        if isinstance(obj, dict):
            if "net_total" in obj and "n" in obj:
                exit_key = path.rsplit(".", 1)[-1] if path else "unknown"
                if preferred_exit and exit_key == preferred_exit:
                    m = _metric_from_dict(obj, param=param or exit_key, exit_key=exit_key, path=path)
                    if m:
                        found.append(m)
                elif is_contract_exit_key(exit_key):
                    m = _metric_from_dict(obj, param=param or exit_key, exit_key=exit_key, path=path)
                    if m:
                        found.append(m)
            for key, value in obj.items():
                next_param = param
                if path in ("", "summary_by_param", "summary_by_k", "summary_by_k_and_bucket") or (
                    path.startswith("summary_by_param.") and path.count(".") == 1
                ):
                    if key not in ("atr_barrier_180s", "atr_barrier_900s", "atr_barrier_1200s") and not is_contract_exit_key(
                        key
                    ):
                        if path == "summary_by_param" or path.startswith("summary_by_k"):
                            next_param = key
                child_path = f"{path}.{key}" if path else key
                walk(value, child_path, next_param)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]", param)

    for top_key in (
        "summary_by_param",
        "summary_by_k",
        "summary_by_k_and_bucket",
        "summary_by_direction",
        "summary_by_param_and_bucket",
        "summary_by_timing_timeout_cohort",
        "summary_by_timing_all_outcomes",
        "phase0_gate",
    ):
        if top_key in payload:
            walk(payload[top_key], top_key)

    # Deduplicate by path
    seen: set[str] = set()
    unique: list[ParamMetrics] = []
    for m in found:
        if m.path not in seen:
            seen.add(m.path)
            unique.append(m)
    return unique


def pick_champion(
    metrics: list[ParamMetrics],
    payload: dict[str, Any],
    *,
    thesis_class: str | None = None,
) -> ChampionRow | None:
    """Pick champion row: phase0 best_passing param first, else max net_total."""
    _ = thesis_class
    phase0 = payload.get("phase0_gate") or {}
    best_passing = phase0.get("best_passing") or {}
    best_param = best_passing.get("param") or best_passing.get("stretch_k")
    contract_exit = contract_exit_from_payload(payload)

    if best_param is not None:
        param_str = str(best_param)
        matches = [
            m
            for m in metrics
            if m.param == param_str and (not contract_exit or m.exit_key == contract_exit)
        ]
        if matches:
            return _to_champion(matches[0], contract_exit)
        if best_passing.get("n"):
            nm = _as_float(best_passing.get("net_mean"))
            nn = int(best_passing["n"])
            return ChampionRow(
                param=param_str,
                exit_key=contract_exit or "?",
                path="phase0_gate.best_passing",
                n=nn,
                gross_mean=_as_float(best_passing.get("gross_mean")),
                net_mean=nm,
                gross_total=_as_float(best_passing.get("gross_total")),
                net_total=_as_float(best_passing.get("net_total"))
                if best_passing.get("net_total") is not None
                else (nn * nm if nm is not None else None),
                contract_exit=contract_exit,
            )

    pool = _metrics_preferred_aggregate(metrics)
    if metrics:
        best = max(pool, key=lambda m: m.net_total if m.net_total is not None else float("-inf"))
        return _to_champion(best, contract_exit)

    # Fallback: best_passing without totals
    if best_passing.get("n"):
        return ChampionRow(
            param=str(best_param or "?"),
            exit_key=contract_exit or "?",
            path="phase0_gate.best_passing",
            n=int(best_passing["n"]),
            gross_mean=_as_float(best_passing.get("gross_mean")),
            net_mean=_as_float(best_passing.get("net_mean")),
            gross_total=None,
            net_total=None,
            contract_exit=contract_exit,
        )
    return None


def _metrics_without_direction_slices(metrics: list[ParamMetrics]) -> list[ParamMetrics]:
    """Exclude Long/Short sub-slices unless they are the only contract rows."""
    filtered = [
        m
        for m in metrics
        if ".Long." not in m.path and ".Short." not in m.path and m.path.count(".Long") == 0
    ]
    return filtered or metrics


def _metrics_preferred_aggregate(metrics: list[ParamMetrics]) -> list[ParamMetrics]:
    """Prefer top-level k/param aggregates over bucket or direction slices."""
    by_k = [
        m
        for m in metrics
        if m.path.startswith("summary_by_k.") and m.path.count(".") == 3
    ]
    by_param = [m for m in metrics if m.path.startswith("summary_by_param.") and m.path.count(".") == 2]
    if by_k or by_param:
        return by_k + by_param
    filtered = _metrics_without_direction_slices(metrics)
    filtered = [m for m in filtered if "summary_by_k_and_bucket" not in m.path]
    return filtered or metrics


def _to_champion(m: ParamMetrics, contract_exit: str | None) -> ChampionRow:
    return ChampionRow(
        param=m.param,
        exit_key=m.exit_key,
        path=m.path,
        n=m.n,
        gross_mean=m.gross_mean,
        net_mean=m.net_mean,
        gross_total=m.gross_total,
        net_total=m.net_total,
        contract_exit=contract_exit or m.exit_key,
    )


def classify_outcome_class(payload: dict[str, Any], champion: ChampionRow | None) -> str:
    """Map payload gates to OUTCOME_REGISTRY outcome_class."""
    outcome_hint = str(payload.get("outcome_hint") or "")
    fp_gate = payload.get("fingerprint_gate") or {}
    phase0 = payload.get("phase0_gate") or {}
    skew_by = payload.get("skew_gate_by_param") or {}

    if champion and champion.n == 0:
        return "design_error"
    if "spec_anchor_mismatch" in outcome_hint or "cfa_fingerprint_fail" in outcome_hint:
        return "design_error"
    if outcome_hint.endswith("_fingerprint_fail_n"):
        return "sample_sparse"
    if outcome_hint.endswith("_fingerprint_fail_direction"):
        return "direction_falsified"
    if outcome_hint.endswith("_fingerprint_fail"):
        w_med = fp_gate.get("w900_stop_less_gross_median")
        if w_med is None:
            w_med = fp_gate.get("w30_stop_less_gross_median")
        min_n = int(fp_gate.get("min_n") or phase0.get("min_n") or 30)
        fp_n = int(fp_gate.get("n") or (champion.n if champion else 0))
        if w_med is not None and float(w_med) <= 0:
            return "direction_falsified"
        if fp_n < min_n:
            return "sample_sparse"
        return "direction_falsified"

    if fp_gate.get("pass") and champion:
        gross = champion.gross_mean
        if gross is not None and gross < JOINT_CONTRACT_GROSS_FLOOR:
            return "fingerprint_contract_mismatch"

    if champion and champion.gross_mean is not None and champion.gross_mean < JOINT_CONTRACT_GROSS_FLOOR:
        if fp_gate and not fp_gate.get("pass"):
            return "fingerprint_contract_mismatch"

    if "fingerprint_pass_g1_fail" in outcome_hint or (
        phase0.get("pass") is False and champion and (champion.gross_mean or 0) < 5
    ):
        return "no_gross_edge"

    if "no_skew_champion" in outcome_hint:
        return "skew_profile_fail"

    if champion and champion.net_total is not None and champion.net_total > 0:
        if phase0.get("pass") and skew_by:
            best_key = (phase0.get("best_passing") or {}).get("param")
            if best_key and skew_by.get(best_key, {}).get("disqualified"):
                return "skew_profile_fail"
        if not phase0.get("pass") and champion.n < int(phase0.get("min_n") or 30):
            return "sample_sparse"
        if phase0.get("pass"):
            return "near_miss_train_positive"

    if champion and champion.net_mean is not None and champion.net_mean <= 0:
        if fp_gate.get("pass"):
            return "execution_gap"
        return "no_gross_edge"

    return "no_gross_edge"


def collect_warnings(payload: dict[str, Any], champion: ChampionRow | None) -> list[str]:
    warnings: list[str] = []
    fp_gate = payload.get("fingerprint_gate") or {}

    # Non-contract positives in payload
    def walk_horizon(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            if "net_total" in obj and "n" in obj:
                key = path.rsplit(".", 1)[-1] if path else ""
                nt = _as_float(obj.get("net_total"))
                if nt is not None and nt > 0 and not is_contract_exit_key(key):
                    if "horizon" in key.lower() or "stop_less" in key.lower():
                        tag = f"NON_CONTRACT_{key}"
                        if tag not in warnings:
                            warnings.append(tag)
            for k, v in obj.items():
                walk_horizon(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk_horizon(v, f"{path}[{i}]")

    walk_horizon(payload)

    if fp_gate.get("pass") and champion and champion.gross_mean is not None:
        if champion.gross_mean < FINGERPRINT_TRAP_GROSS_CEILING:
            warnings.append("FINGERPRINT_TRAP_SUSPECT")

    if champion and champion.net_total is not None and champion.net_total > 0:
        phase0 = payload.get("phase0_gate") or {}
        if not phase0.get("pass"):
            warnings.append("TRAIN_NET_POSITIVE_BUT_PHASE0_FAIL")

    return warnings


def build_gate_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Build gate_summary block for counterfactual JSON."""
    metrics = extract_contract_metrics(payload)
    thesis_class = payload.get("thesis_class") or (payload.get("phase0_gate") or {}).get("thesis_class")
    champion = pick_champion(metrics, payload, thesis_class=thesis_class)
    outcome_class = classify_outcome_class(payload, champion)
    warnings = collect_warnings(payload, champion)

    champion_dict: dict[str, Any] | None = None
    if champion:
        champion_dict = {
            "param": champion.param,
            "exit_key": champion.exit_key,
            "path": champion.path,
            "n": champion.n,
            "gross_mean": champion.gross_mean,
            "net_mean": champion.net_mean,
            "gross_total": champion.gross_total,
            "net_total": champion.net_total,
            "contract_exit": champion.contract_exit,
        }

    return {
        "champion": champion_dict,
        "outcome_class": outcome_class,
        "warnings": warnings,
        "contract_exit": contract_exit_from_payload(payload),
        "thesis_class": thesis_class,
    }


def format_gate_report_table(
    champion: ChampionRow | dict[str, Any] | None,
    *,
    title: str = "Train 帳面（契約出場 · 非 stop-less）",
) -> str:
    """Markdown table for gate_report.md first page."""
    if champion is None:
        return f"## {title}\n\n（無契約出場樣本）\n"

    if isinstance(champion, dict):
        row = champion
    else:
        row = {
            "param": champion.param,
            "n": champion.n,
            "gross_total": champion.gross_total,
            "net_total": champion.net_total,
            "gross_mean": champion.gross_mean,
            "net_mean": champion.net_mean,
            "contract_exit": champion.contract_exit,
        }

    def fmt(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.1f}"
        return str(v)

    lines = [
        f"## {title}",
        "",
        "| 冠軍/最佳 | n | gross_total | net_total | gross/趟 | net/趟 | 契約 exit |",
        "|-----------|--:|------------:|----------:|---------:|-------:|-----------|",
        (
            f"| {row.get('param', '?')} | {row.get('n', '?')} | "
            f"{fmt(row.get('gross_total'))} | **{fmt(row.get('net_total'))}** | "
            f"{fmt(row.get('gross_mean'))} | {fmt(row.get('net_mean'))} | "
            f"{row.get('contract_exit', '—')} |"
        ),
        "",
    ]
    return "\n".join(lines)


def evaluate_mean_robust_appeal(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only §3.1 check for Holdout v2.3 Class Appeal (frozen param, no grid)."""
    summary = build_gate_summary(payload)
    champ = summary.get("champion") or {}
    phase0 = payload.get("phase0_gate") or {}
    disqualify: list[str] = []

    gross_mean = champ.get("gross_mean")
    net_mean = champ.get("net_mean")
    n = champ.get("n")
    gross_median = None
    param = champ.get("param")
    contract_exit = champ.get("contract_exit") or contract_exit_from_payload(payload)
    if param and contract_exit:
        block = (payload.get("summary_by_param") or {}).get(param, {}).get(contract_exit, {})
        gross_median = _as_float(block.get("gross_median"))

    if gross_mean is None or gross_mean <= 5:
        disqualify.append("G1_gross_mean")
    if net_mean is None or net_mean <= 0:
        disqualify.append("G2_net_mean")
    if n is None or int(n) < 30:
        disqualify.append("G3_n")
    if gross_median is not None and gross_median <= -5:
        disqualify.append("gross_median")

    passed = not disqualify and phase0.get("pass") is True
    return {
        "eligible": summary.get("outcome_class") == "skew_profile_fail"
        and (champ.get("net_total") or 0) > 0,
        "mean_robust_pass": passed,
        "disqualify": disqualify,
        "champion_param": param,
        "gross_median": gross_median,
        "note": "Read-only · Holdout v2.3 §2.3 · does not reopen MVPClosed without TXF sign-off",
    }


def format_warnings_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["### 警示", ""]
    for w in warnings:
        if w.startswith("NON_CONTRACT"):
            lines.append(f"- `{w}` — **不得當 gate**")
        elif w == "FINGERPRINT_TRAP_SUSPECT":
            lines.append("- `FINGERPRINT_TRAP_SUSPECT` — fingerprint 通過但契約 gross/趟 < 3")
        else:
            lines.append(f"- `{w}`")
    lines.append("")
    return "\n".join(lines)
