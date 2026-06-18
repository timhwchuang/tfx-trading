"""EXEC_AUDIT for kernel pending lifecycle (FT-001 Phase 2)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class ExecAudit:
    """Kernel execution audit (pending arm/cancel/timeout, position sync).

    Emitted as "EXEC_AUDIT {json}".
    """

    audit_schema_version: int = 1
    event_type: str = ""  # pending_armed | pending_cancelled | pending_timeout | position_sync
    ts: int = 0
    signal_id: str = ""

    # pending_armed
    order_id: str = ""
    limit_price: float = 0.0
    direction: str = ""

    # pending_cancelled
    tag: str = ""

    # pending_timeout
    pending_sec: int = 0

    # position_sync
    qty_before: int = 0
    qty_after: int = 0
    position_dir: str = ""


def format_exec_audit(audit: ExecAudit) -> str:
    """Compact JSON matching the audit contract.

    Always preserve MUST fields per SPEC §5.3 even when falsy (order_id, tag, limit_price etc.).
    """
    raw = asdict(audit)
    payload: dict = {}
    must = {
        "audit_schema_version", "event_type", "ts", "signal_id",
        "order_id", "limit_price", "direction", "tag", "pending_sec",
        "qty_before", "qty_after", "position_dir",
    }
    for k in must:
        if k in raw:
            payload[k] = raw[k]
    for k, v in raw.items():
        if k in payload:
            continue
        if v not in ("", None):
            payload[k] = v
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
