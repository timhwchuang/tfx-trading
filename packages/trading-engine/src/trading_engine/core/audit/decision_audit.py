"""Decision audit (non-OrderSignal decisions from strategy, e.g. momentum_armed)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class DecisionAudit:
    """Structured decision event for audit replay (FT-001).

    Emitted via logger "DECISION_AUDIT {json}" for events that do not produce OrderSignal
    (armed, pullback_candidate, veto, timeout, risk_blocked).
    """

    audit_schema_version: int = 1
    event_type: str = ""
    ts: int = 0
    episode_id: str = ""

    # Common for armed / veto / timeout
    direction: str = ""  # "Long" | "Short"
    trigger_price: float = 0.0
    price: float = 0.0
    vol_1s: int = 0
    buy_ratio: float = 0.0
    sell_ratio: float = 0.0
    vol_threshold: float = 0.0
    multiplier: float = 0.0
    atr: float = 0.0
    vwap: float = 0.0

    # pullback
    dist_vwap: float = 0.0
    near_vwap: bool = False
    vol_dried_up: bool = False

    # timeout
    elapsed_sec: int = 0

    # veto / risk
    reason: str = ""
    trend_dir: str = ""
    trend_strength: float = 0.0
    block_reason: str = ""
    consecutive_loss: int = 0

    # pressure context (Phase 3+)
    consecutive_veto_streak: int = 0
    consecutive_timeout_streak: int = 0
    episodes_since_last_entry: int = 0

    # linking
    parent_id: str = ""

    # FT-002 structure filter (Phase 4)
    momentum_dir: str = ""
    structure_algo_version: int = 0
    structure_bias: str = ""
    structure_strength: float = 0.0
    structure_in_discount: bool = False
    structure_in_premium: bool = False
    structure_fvg_low: float | None = None
    structure_fvg_high: float | None = None
    active_fvg_side: str = ""
    structure_sweep_reclaim: bool = False


def format_decision_audit(audit: DecisionAudit) -> str:
    """Serialize matching {prefix} {compact-json} contract.

    Always keep MUST fields per SPEC even if zero (e.g. dist_vwap=0.0, elapsed_sec=0).
    Only drop truly empty string/None defaults for optional fields.
    For momentum_armed: explicitly clean, omit irrelevant 0s and pressure ctx streaks (per SPEC examples; pressure ctx for veto/timeout/risk_blocked).
    """
    raw = asdict(audit)
    payload: dict = {}
    et = audit.event_type
    # structural always
    for k in ("audit_schema_version", "event_type", "ts", "episode_id"):
        if k in raw:
            payload[k] = raw[k]

    structure_keys = (
        "structure_algo_version",
        "structure_bias",
        "structure_strength",
        "structure_in_discount",
        "structure_in_premium",
        "structure_fvg_low",
        "structure_fvg_high",
        "active_fvg_side",
        "structure_sweep_reclaim",
    )

    if et == "momentum_armed":
        armed_must = {"direction", "trigger_price", "vol_1s", "buy_ratio", "sell_ratio", "vol_threshold", "multiplier", "vwap", "atr"}
        for k in armed_must:
            if k in raw:
                payload[k] = raw[k]
        for k in structure_keys:
            if k in raw and raw[k] not in (None, "", 0, 0.0, False):
                payload[k] = raw[k]
        # explicitly do not add 0-value fields like price, consecutive_*=0 etc for armed (clean per SPEC examples)
    elif et == "structure_veto":
        for k in (
            "direction",
            "price",
            "vol_1s",
            "reason",
            "vwap",
            "momentum_dir",
            "structure_algo_version",
            "structure_bias",
            "structure_strength",
            "structure_in_discount",
            "structure_in_premium",
            "structure_fvg_low",
            "structure_fvg_high",
            "active_fvg_side",
            "structure_sweep_reclaim",
        ):
            if k in raw and raw[k] not in (None, ""):
                payload[k] = raw[k]
    else:
        # for timeout/veto/risk keep price etc if set
        for k in ("direction", "trigger_price", "price", "vol_1s", "buy_ratio", "sell_ratio", "elapsed_sec", "reason", "trend_dir", "trend_strength", "block_reason", "atr", "consecutive_loss"):
            if k in raw and raw[k] not in (None, "", 0, 0.0, False) or k in ("price", "elapsed_sec"):
                payload[k] = raw[k]

    # include streak/pressure ctx (even 0) only for non-armed events (Phase 3 SPEC: applicable to veto/timeout/risk_blocked)
    # armed remains clean (no irrelevant zeros)
    for k in ("consecutive_veto_streak", "consecutive_timeout_streak", "episodes_since_last_entry", "parent_id"):
        if k in raw:
            v = raw[k]
            if et == "momentum_armed" and v in (0, 0.0, None, False, ""):
                continue
            payload[k] = v

    # other non-empty (armed stays clean — no stray zero defaults)
    if et != "momentum_armed":
        for k, v in raw.items():
            if k in payload:
                continue
            if v not in ("", None):
                payload[k] = v
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
