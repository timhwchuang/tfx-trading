"""P1-5: structured signal audit log (one JSON line per OrderSignal)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class SignalAudit:
    intent: str
    direction: str
    price: float
    ts: int
    vol_1s: int = 0
    buy_ratio: float = 0.0
    sell_ratio: float = 0.0
    atr: float = 0.0
    multiplier: float = 0.0
    vol_threshold: float = 0.0
    vwap: float = 0.0
    reason: str = ""
    trend_dir: str = ""
    trend_strength: float = 0.0
    trail_points_used: float = 0.0
    # FT-001 optional (Phase 1+)
    episode_id: str = ""
    signal_id: str = ""
    elapsed_since_arm_sec: int = 0
    dist_vwap: float = 0.0
    entry_price: float = 0.0
    hold_ticks: int = 0
    in_grace: bool = False
    hard_stop_level: float = 0.0
    vwap_stop_level: float = 0.0
    trailing_peak: float = 0.0


def format_signal_audit(audit: SignalAudit) -> str:
    payload = asdict(audit)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
