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

    # pressure context (Phase 3+)
    consecutive_veto_streak: int = 0
    consecutive_timeout_streak: int = 0
    episodes_since_last_entry: int = 0

    # linking
    parent_id: str = ""


def format_decision_audit(audit: DecisionAudit) -> str:
    """Serialize matching {prefix} {compact-json} contract.

    Always keep MUST fields per SPEC even if zero (e.g. dist_vwap=0.0, elapsed_sec=0).
    Only drop truly empty string/None defaults for optional fields.
    """
    raw = asdict(audit)
    payload: dict = {}
    # Always keep structural + MUST for current events
    must_fields = {
        "audit_schema_version", "event_type", "ts", "episode_id",
        # momentum_armed MUST
        "direction", "trigger_price", "vol_1s", "buy_ratio", "sell_ratio",
        "vol_threshold", "multiplier",
        # other potential MUST that can legitimately be 0
        "dist_vwap", "elapsed_sec", "price",
    }
    for k in must_fields:
        if k in raw:
            payload[k] = raw[k]

    for k, v in raw.items():
        if k in payload:
            continue
        # Drop only empty strings and None for optional fields
        if v not in ("", None):
            payload[k] = v
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
