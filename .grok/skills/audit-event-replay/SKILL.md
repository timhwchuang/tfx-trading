---
name: audit-event-replay
description: >
  FT-001 audit event replay for tfx-trading: DECISION/SIGNAL/EXEC/FILL audit contract,
  episode_id timeline, uat_report replay. Use when implementing or reviewing FT-001,
  qualified audit fields, episode funnel, or /audit-event-replay.
---

# Audit Event Replay (FT-001)

Read and follow the feature contract before coding or reviewing:

```
docs/features/audit-event-replay/SPEC.md
docs/features/audit-event-replay/PLAN.md
docs/features/audit-event-replay/REVIEW.md
```

Feature board and ft SOP:

```
docs/features/README.md
```

Current stable audit (transition period):

```
apps/trading-app/SPEC.md
```

## Invocation

User runs `/audit-event-replay` or asks to implement/review audit replay, episode timeline, DECISION_AUDIT, or FT-001.

## Steps

1. Load SPEC + PLAN; check PLAN phase checkboxes for current scope.
2. **Draft ft**: design truth is feature SPEC; do not contradict app SPEC without noting migration phase.
3. **Implementing**: only touch files listed in active PLAN phase; add tests per SPEC §9 DoD.
4. **Log contract**: new prefixes/fields MUST match SPEC §3–§5; update `uat_report` / determinism when changing consumers.
5. **Landed**: MUST merge stable fields into app SPEC §Integration contracts + CHANGELOG (see PLAN Land checklist).

## Phase guardrails

- Do not enable live or change `simulation: false`.
- New JSON fields MUST be optional until Phase 4 (backward compat).
- `pullback_candidate` and `risk_blocked` MUST use throttling per SPEC §5.1.

## Key paths

| Topic | Location |
|-------|----------|
| SignalAudit | `packages/trading-engine/src/trading_engine/core/audit/signal_audit.py` |
| Strategy emits | `packages/strategies/vwap-momentum/src/strategy_vwap_momentum/strategy.py` |
| FillAudit | `apps/trading-app/src/observability.py` |
| Reporting | `apps/trading-app/src/reporting/uat_report.py` |
| Determinism | `apps/trading-app/src/sweep/determinism_check.py` |